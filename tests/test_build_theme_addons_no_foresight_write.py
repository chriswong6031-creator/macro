"""Regression: build_theme_addons must NOT write foresight_cascade.json.

Before this fix, build_theme_addons.main() called compute_foresight_cascade and dumped
the result to site/basketdata/foresight_cascade.json, clobbering the richer file that
scripts.build_foresight had already written (which carries the `health` key and the
policy-calendar enrichment). scripts.build_foresight is now the sole writer.

These tests are hermetic: all engine calls are patched out so the test runs without
any real data on disk.
"""
from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_module(name: str) -> types.ModuleType:
    """Return a stub module registered in sys.modules under `name`."""
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _patch_all_engines(monkeypatch):
    """Stub out every engine import that build_theme_addons.main() does so the
    test stays hermetic even when data/ files are absent."""
    # etf_pulse
    ep_mod = _make_fake_module("engine.etf_pulse")
    ep_mod.compute_etf_pulse = lambda: {"etf": "stub"}

    # vol_sentiment
    vs_mod = _make_fake_module("engine.vol_sentiment")
    vs_mod.compute_vol_sentiment = lambda: {"vol": "stub"}

    # theme_extension
    te_mod = _make_fake_module("engine.theme_extension")
    te_mod.compute_theme_extension = lambda region: {"region": region}

    # basket_member_context
    bmc_mod = _make_fake_module("engine.basket_member_context")
    bmc_mod.compute_member_context = lambda region: {"region": region}

    # edgar_fts — drip call; non-fatal
    fts_mod = _make_fake_module("collectors.edgar_fts")
    fts_mod.fetch_bottleneck_hits = lambda: None

    # theme_revisions
    tr_mod = _make_fake_module("engine.theme_revisions")
    tr_mod.compute_theme_revisions = lambda write_ledger=False: {"rv": "stub"}

    # bottleneck
    bn_mod = _make_fake_module("engine.bottleneck")
    bn_mod.compute_bottleneck = lambda write_ledger=False: {"bn": "stub"}

    # eightk enrichment — optional, failure is non-fatal
    e8_col = _make_fake_module("collectors.edgar_8k")
    e8_col.enrich_contract_amounts = lambda df, incremental=False: df

    e8_eng = _make_fake_module("engine.eightk_magnitude")
    e8_eng.compute_eightk_magnitude = lambda write_ledger=False: {"mag": "stub"}


# ---------------------------------------------------------------------------
# Core regression
# ---------------------------------------------------------------------------

def test_main_does_not_write_foresight_cascade(tmp_path, monkeypatch):
    """main() must not create foresight_cascade.json — build_foresight owns that file."""
    # Point config.ROOT at tmp_path so _dump writes there
    import lib.config as cfg
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    _patch_all_engines(monkeypatch)

    # Ensure pandas is available for the eightk block (it checks events_path.exists())
    # No parquet there, so the block skips gracefully.

    # Force module reload so patched imports are picked up
    import scripts.build_theme_addons as bta
    importlib.reload(bta)

    rc = bta.main()

    cascade_path = tmp_path / "site" / "basketdata" / "foresight_cascade.json"
    assert not cascade_path.exists(), (
        "build_theme_addons must not write foresight_cascade.json — "
        "scripts.build_foresight is the sole owner of that artifact"
    )
    assert rc == 0


def test_main_still_writes_theme_revisions_and_bottleneck(tmp_path, monkeypatch):
    """Removing foresight_cascade write must not break theme_revisions.json / bottleneck.json."""
    import lib.config as cfg
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    _patch_all_engines(monkeypatch)

    import scripts.build_theme_addons as bta
    importlib.reload(bta)

    bta.main()

    fdir = tmp_path / "site" / "basketdata"
    rv_path = fdir / "theme_revisions.json"
    bn_path = fdir / "bottleneck.json"

    assert rv_path.exists(), "theme_revisions.json must still be written"
    assert bn_path.exists(), "bottleneck.json must still be written"

    rv = json.loads(rv_path.read_text())
    bn = json.loads(bn_path.read_text())
    assert rv == {"rv": "stub"}
    assert bn == {"bn": "stub"}


def test_build_theme_addons_module_does_not_import_compute_foresight_cascade():
    """compute_foresight_cascade must not be imported at module level or inside main().

    We inspect the source for the call signature that used to be the clobber site.
    This is a read-only static check — it will catch re-introduction of the write.
    """
    src_path = Path(__file__).resolve().parent.parent / "scripts" / "build_theme_addons.py"
    src = src_path.read_text()
    assert "compute_foresight_cascade" not in src, (
        "compute_foresight_cascade found in build_theme_addons.py — "
        "this function must only be called by scripts.build_foresight"
    )
