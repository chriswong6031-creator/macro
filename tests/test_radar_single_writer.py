"""Regression: radar.json must have EXACTLY ONE writer (scripts/build_baskets.py).

neural-web W0 PR5 — single-writer discipline for site/basketdata/radar.json.

Two rot patterns were fixed:
  ROT A: scripts/build_intelligence.py previously called _crosssurface_radar()
          which mutated radar.json in-place after build_baskets.py wrote it.
          Fix: build_intelligence now writes radar_news.json as its OWN artifact.

  ROT B: scripts/build_radar_plus.py previously read radar.json, called
          radar_plus.enrich(), then wrote the mutated result back to radar.json.
          Fix: build_radar_plus now writes radar_enriched.json as its OWN artifact.

These tests enforce the fix statically (no live data needed) and dynamically
(tmp_path mocks verifying the correct files are written / NOT written).
"""
from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_mod(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _stub_config_load(monkeypatch):
    """Patch config.load() to return a minimal dict with site_dir='site'.
    Also clears the lru_cache so the patched value is used."""
    import lib.config as cfg
    cfg.load.cache_clear()
    monkeypatch.setattr(cfg, "load", lambda: {"storage": {"site_dir": "site"}})


def _stub_intelligence_engines():
    """Stub engine.intelligence so build_intelligence.build() stays hermetic."""
    mod = _make_mod("engine.intelligence")
    mod.load_and_build = lambda: {"n_tickers": 0, "n_with_both": 0}
    return mod


def _stub_radar_plus_engines():
    """Stub engine.radar_plus and engine.radar_ticker so build_radar_plus.build() is hermetic."""
    rp = _make_mod("engine.radar_plus")
    rp.enrich = lambda radar, **kw: radar  # no-op enrichment

    rt = _make_mod("engine.radar_ticker")
    rt.build = lambda: {"n": 0, "n_divergences": 0, "tickers": []}
    return rp, rt


# ---------------------------------------------------------------------------
# STATIC CHECKS — source-level enforcement
# ---------------------------------------------------------------------------

class TestStaticRadarSingleWriter:
    """Source text must not contain the patterns that cause the rot."""

    def test_build_intelligence_does_not_write_radar_json(self):
        """def _crosssurface_radar must not exist; radar.json must not be opened for writing."""
        src = (Path(__file__).resolve().parent.parent / "scripts" / "build_intelligence.py").read_text()
        # The function definition (not a mention in comments) must be gone.
        assert "def _crosssurface_radar" not in src, (
            "def _crosssurface_radar found in build_intelligence.py — "
            "this function was the source of the radar.json second-writer rot and must not exist"
        )
        # There must be no write_text call on a path ending in radar.json in this module.
        # The pattern 'radar.json").write_text' would reintroduce rot.
        assert 'radar.json").write_text' not in src, (
            "build_intelligence.py must never write to radar.json"
        )

    def test_build_radar_plus_does_not_write_to_radar_json(self):
        """build_radar_plus must NOT write back to radar.json — it must write radar_enriched.json."""
        src = (Path(__file__).resolve().parent.parent / "scripts" / "build_radar_plus.py").read_text()
        # The fix: enriched_p (radar_enriched.json) must be written, not radar_p (radar.json).
        assert "radar_enriched.json" in src, (
            "build_radar_plus.py must write radar_enriched.json as its own artifact"
        )
        # Ensure the old pattern (write back to radar_p) is gone.
        # The original rot was: radar_p.write_text(json.dumps(radar, default=str))
        # After the fix radar_p is read-only; only enriched_p is written.
        assert "radar_p.write_text" not in src, (
            "build_radar_plus.py must not write to radar_p (radar.json); "
            "write to radar_enriched.json instead"
        )

    def test_build_intelligence_writes_radar_news(self):
        """build_intelligence must reference radar_news.json as its output artifact."""
        src = (Path(__file__).resolve().parent.parent / "scripts" / "build_intelligence.py").read_text()
        assert "radar_news.json" in src, (
            "build_intelligence.py must write radar_news.json as its own artifact "
            "(not cross-surface headlines onto radar.json)"
        )


# ---------------------------------------------------------------------------
# DYNAMIC CHECKS — verify correct files written in tmp_path
# ---------------------------------------------------------------------------

class TestDynamicRadarSingleWriter:
    """Run the patched builders in tmp_path and assert the correct artifacts are written."""

    def test_build_intelligence_writes_radar_news_not_radar(self, tmp_path, monkeypatch):
        """build_intelligence.build() must write radar_news.json and NOT touch radar.json."""
        import lib.config as cfg
        monkeypatch.setattr(cfg, "ROOT", tmp_path)
        _stub_config_load(monkeypatch)

        _stub_intelligence_engines()

        # Pre-populate financial.json with one basket having headlines.
        news_dir = tmp_path / "site" / "news"
        news_dir.mkdir(parents=True, exist_ok=True)
        (news_dir / "financial.json").write_text(json.dumps({
            "baskets": {
                "ai_infra": {
                    "headlines": [
                        {"title": "AI chip shortage", "url": "https://example.com/1",
                         "source": "Reuters", "sentiment": "neg"},
                        {"title": "NVDA beats estimates", "url": "https://example.com/2",
                         "source": "Bloomberg", "sentiment": "pos"},
                    ]
                }
            }
        }))

        # Ensure site/basketdata/ exists (build_intelligence must NOT create radar.json there).
        bdata_dir = tmp_path / "site" / "basketdata"
        bdata_dir.mkdir(parents=True, exist_ok=True)

        import scripts.build_intelligence as bi
        importlib.reload(bi)
        bi.build(write=True)

        radar_p = bdata_dir / "radar.json"
        radar_news_p = bdata_dir / "radar_news.json"

        assert not radar_p.exists(), (
            "build_intelligence must NOT write or create radar.json — "
            "only build_baskets may write that file"
        )
        assert radar_news_p.exists(), (
            "build_intelligence must write radar_news.json as its own artifact"
        )
        rn = json.loads(radar_news_p.read_text())
        assert "baskets" in rn, "radar_news.json must have a 'baskets' top-level key"
        assert "ai_infra" in rn["baskets"], "ai_infra basket headlines must appear in radar_news.json"
        assert len(rn["baskets"]["ai_infra"]["headlines"]) == 2

    def test_build_intelligence_does_not_mutate_existing_radar(self, tmp_path, monkeypatch):
        """build_intelligence.build() must leave an existing radar.json byte-identical."""
        import lib.config as cfg
        monkeypatch.setattr(cfg, "ROOT", tmp_path)
        _stub_config_load(monkeypatch)

        _stub_intelligence_engines()

        bdata_dir = tmp_path / "site" / "basketdata"
        bdata_dir.mkdir(parents=True, exist_ok=True)
        # Write a sentinel radar.json — it must be unchanged after build_intelligence runs.
        original_content = '{"flags":[],"sentinel":"MUST_NOT_CHANGE"}'
        (bdata_dir / "radar.json").write_text(original_content)

        news_dir = tmp_path / "site" / "news"
        news_dir.mkdir(parents=True, exist_ok=True)
        (news_dir / "financial.json").write_text(json.dumps({"baskets": {}}))

        import scripts.build_intelligence as bi
        importlib.reload(bi)
        bi.build(write=True)

        assert (bdata_dir / "radar.json").read_text() == original_content, (
            "build_intelligence must NOT mutate an existing radar.json"
        )

    def test_build_radar_plus_writes_enriched_not_radar(self, tmp_path, monkeypatch):
        """build_radar_plus.build() must write radar_enriched.json and NOT touch radar.json."""
        import lib.config as cfg
        monkeypatch.setattr(cfg, "ROOT", tmp_path)
        _stub_config_load(monkeypatch)

        _stub_radar_plus_engines()

        bdata_dir = tmp_path / "site" / "basketdata"
        bdata_dir.mkdir(parents=True, exist_ok=True)
        original_radar = '{"flags":[{"basket":"defense","state":"POSITIVE_DIVERGENCE"}]}'
        (bdata_dir / "radar.json").write_text(original_radar)

        import scripts.build_radar_plus as brp
        importlib.reload(brp)
        result = brp.build(write=True)

        assert result["radar_enriched"] is True
        # radar.json must be byte-identical to what build_baskets wrote.
        assert (bdata_dir / "radar.json").read_text() == original_radar, (
            "build_radar_plus must NOT modify radar.json — write radar_enriched.json only"
        )
        enriched_p = bdata_dir / "radar_enriched.json"
        assert enriched_p.exists(), (
            "build_radar_plus must write radar_enriched.json as its own artifact"
        )
        enriched = json.loads(enriched_p.read_text())
        assert "flags" in enriched, "radar_enriched.json must contain a 'flags' list"

    def test_build_radar_plus_degrades_when_radar_absent(self, tmp_path, monkeypatch):
        """build_radar_plus.build() must degrade gracefully when radar.json is absent."""
        import lib.config as cfg
        monkeypatch.setattr(cfg, "ROOT", tmp_path)
        _stub_config_load(monkeypatch)

        _stub_radar_plus_engines()

        import scripts.build_radar_plus as brp
        importlib.reload(brp)
        result = brp.build(write=True)

        assert result["radar_enriched"] is False, (
            "radar_enriched must be False when radar.json is absent"
        )
        enriched_p = tmp_path / "site" / "basketdata" / "radar_enriched.json"
        assert not enriched_p.exists(), (
            "radar_enriched.json must not be written when radar.json is absent"
        )


# ---------------------------------------------------------------------------
# SYNAPSE.YML check — known_extra_writers for site-radar-json must be empty
# ---------------------------------------------------------------------------

class TestSynapseRadarSingleWriter:
    def test_synapse_radar_json_no_extra_writers(self):
        """config/synapse.yml: site-radar-json.known_extra_writers must be an empty list."""
        # Parse the YAML text without requiring PyYAML — search for the section.
        src = (Path(__file__).resolve().parent.parent / "config" / "synapse.yml").read_text()
        # Find the site-radar-json block and assert known_extra_writers is empty.
        # The pattern we look for: "known_extra_writers: []" in the site-radar-json section.
        # We locate the section and scan forward until the next top-level artifact entry.
        lines = src.splitlines()
        in_block = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "site-radar-json:":
                in_block = True
                continue
            if in_block:
                # Another artifact entry ends the block (two-space-indented key: at top)
                if stripped and not line.startswith("  ") and ":" in stripped:
                    break
                if "known_extra_writers:" in stripped:
                    # The value must be "[]" on the same line for an empty list.
                    assert "[]" in line, (
                        f"site-radar-json.known_extra_writers must be empty ([]); "
                        f"found: {line.strip()!r} — remove second-writer entries after the W0 PR5 fix"
                    )
                    return  # found and passed
        # If we never found known_extra_writers in the block, that is also acceptable
        # (could be absent → implicitly empty). But if we failed the assert above we'd have raised.
