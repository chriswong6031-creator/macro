"""WP-RESOLVER — canonical ThetaData store resolver tests (CI-safe, hermetic).

Covers engine.thetadata_store.resolve_thetadata_store:
  - env tier resolves (source=env) when the path has store content
  - env set-but-missing warns loudly and falls through
  - empty-stub dirs (exist, but no eod/oi/greeks subdirs) do NOT resolve —
    that is the exact shape of the options_witness 0/18 incident
  - required=True raises RuntimeError naming every path tried + the purpose
  - store_root() back-compat wrapper still returns a Path

Plus the incident regression shape for engine.theme_options_witness:
  - _theta_store() delegates to the canonical resolver (per-module hardcoded
    fallback chain removed)
  - build() with NO resolvable store leaves a fresh committed real artifact
    untouched (keep-last-real) instead of clobbering it with an all-suppressed
    output.

All machine-specific tiers (env / data_dir / ops-wt) are monkeypatched to
tmp_path so these tests never touch a real store.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lib.config as libconfig  # noqa: E402
from engine import thetadata_store as tds  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers                                                                       #
# --------------------------------------------------------------------------- #

def _mk_store(p: Path, tiers=("eod",)) -> Path:
    """Create a directory that passes the content check (>=1 tier subdir)."""
    for t in tiers:
        (p / t).mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture()
def isolated_chain(tmp_path, monkeypatch):
    """Point every resolver tier at tmp_path so nothing machine-specific leaks in.

    Returns the (empty, non-existent) data_dir-tier store path; individual tests
    create content where they need it.
    """
    repo_data = tmp_path / "repo_data"
    repo_data.mkdir()
    monkeypatch.setattr(libconfig, "data_dir", lambda: repo_data)
    monkeypatch.setattr(tds, "_OPS_WT_STORE", tmp_path / "no_ops_wt")
    monkeypatch.delenv("THETADATA_STORE", raising=False)
    return repo_data / "thetadata_eod"


# --------------------------------------------------------------------------- #
# resolve_thetadata_store                                                       #
# --------------------------------------------------------------------------- #

class TestResolveChain:
    def test_env_valid_store_resolves_source_env(self, tmp_path, monkeypatch,
                                                 isolated_chain, caplog):
        env_store = _mk_store(tmp_path / "env_store", tiers=("eod", "oi"))
        monkeypatch.setenv("THETADATA_STORE", str(env_store))
        with caplog.at_level(logging.INFO, logger="engine.thetadata_store"):
            result = tds.resolve_thetadata_store(purpose="unit-test")
        assert result == env_store
        assert any("source=env" in r.message for r in caplog.records), \
            "resolver must log the resolution source (env)"
        assert any("unit-test" in r.message for r in caplog.records), \
            "resolver must log the purpose"

    def test_env_missing_warns_and_falls_through(self, tmp_path, monkeypatch,
                                                 isolated_chain, caplog):
        monkeypatch.setenv("THETADATA_STORE", str(tmp_path / "does_not_exist"))
        data_store = _mk_store(isolated_chain, tiers=("oi",))
        with caplog.at_level(logging.INFO, logger="engine.thetadata_store"):
            result = tds.resolve_thetadata_store(purpose="unit-test")
        assert result == data_store, "must fall through to the data_dir tier"
        warned = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("does not exist" in r.message for r in warned), \
            "set-but-missing THETADATA_STORE must warn loudly"
        assert any("source=data_dir" in r.message for r in caplog.records)

    def test_empty_stub_does_not_resolve(self, tmp_path, monkeypatch,
                                         isolated_chain, caplog):
        """The incident shape: a dir that EXISTS but holds no eod/oi/greeks."""
        stub = tmp_path / "stub_store"
        stub.mkdir()
        (stub / "random_file.txt").write_text("not a store")
        monkeypatch.setenv("THETADATA_STORE", str(stub))
        with caplog.at_level(logging.INFO, logger="engine.thetadata_store"):
            result = tds.resolve_thetadata_store(purpose="unit-test")
        assert result is None, "an empty stub dir must NOT resolve"
        warned = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("empty stub" in r.message for r in warned)

    def test_ops_wt_tier_resolves_last(self, tmp_path, monkeypatch,
                                       isolated_chain, caplog):
        ops = _mk_store(tmp_path / "ops_wt_store", tiers=("greeks",))
        monkeypatch.setattr(tds, "_OPS_WT_STORE", ops)
        with caplog.at_level(logging.INFO, logger="engine.thetadata_store"):
            result = tds.resolve_thetadata_store(purpose="unit-test")
        assert result == ops
        assert any("source=ops-wt" in r.message for r in caplog.records)

    def test_env_beats_data_dir_and_ops_wt(self, tmp_path, monkeypatch,
                                           isolated_chain):
        env_store = _mk_store(tmp_path / "env_store")
        _mk_store(isolated_chain)
        ops = _mk_store(tmp_path / "ops_wt_store")
        monkeypatch.setattr(tds, "_OPS_WT_STORE", ops)
        monkeypatch.setenv("THETADATA_STORE", str(env_store))
        assert tds.resolve_thetadata_store() == env_store

    def test_nothing_resolves_returns_none(self, isolated_chain, caplog):
        with caplog.at_level(logging.ERROR, logger="engine.thetadata_store"):
            assert tds.resolve_thetadata_store(purpose="unit-test") is None
        assert any("NONE" in r.message for r in caplog.records), \
            "total resolution failure must log loudly"

    def test_required_true_raises_naming_tried_paths(self, tmp_path, monkeypatch,
                                                     isolated_chain):
        env_path = tmp_path / "missing_env_store"
        monkeypatch.setenv("THETADATA_STORE", str(env_path))
        with pytest.raises(RuntimeError) as exc:
            tds.resolve_thetadata_store(required=True, purpose="unit-test-required")
        msg = str(exc.value)
        assert "unit-test-required" in msg, "message must name the purpose"
        assert str(env_path) in msg, "message must name the env path tried"
        assert str(isolated_chain) in msg, "message must name the data_dir path tried"
        assert str(tmp_path / "no_ops_wt") in msg, "message must name the ops-wt path tried"


# --------------------------------------------------------------------------- #
# store_root back-compat                                                        #
# --------------------------------------------------------------------------- #

class TestStoreRootBackCompat:
    def test_store_root_still_returns_path_when_missing(self, tmp_path,
                                                        monkeypatch):
        missing = tmp_path / "not_there"
        monkeypatch.setenv("THETADATA_STORE", str(missing))
        result = tds.store_root()
        assert isinstance(result, Path)
        assert result == missing, "back-compat: env value is returned even when missing"

    def test_store_root_override_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("THETADATA_STORE", str(tmp_path / "env_store"))
        explicit = tmp_path / "explicit"
        assert tds.store_root(override=explicit) == explicit

    def test_store_root_warns_once_on_missing(self, tmp_path, monkeypatch, caplog):
        missing = tmp_path / "warn_once_store"
        monkeypatch.setenv("THETADATA_STORE", str(missing))
        tds._WARNED_MISSING_ROOTS.discard(str(missing))
        with caplog.at_level(logging.WARNING, logger="engine.thetadata_store"):
            tds.store_root()
            tds.store_root()
        hits = [r for r in caplog.records if str(missing) in r.message]
        assert len(hits) == 1, "missing-root warning must fire once per path, not per read"


# --------------------------------------------------------------------------- #
# theme_options_witness regression (0/18 all-suppressed incident shape)         #
# --------------------------------------------------------------------------- #

class TestWitnessIncidentRegression:
    def test_theta_store_delegates_to_canonical_resolver(self, tmp_path,
                                                         monkeypatch):
        from engine import theme_options_witness as mod
        sentinel = _mk_store(tmp_path / "sentinel_store", tiers=("oi",))
        calls = {}

        def fake_resolver(required=False, purpose=""):
            calls["required"] = required
            calls["purpose"] = purpose
            return sentinel

        monkeypatch.setattr(tds, "resolve_thetadata_store", fake_resolver)
        assert mod._theta_store() == sentinel
        assert calls["required"] is False
        assert "theme_options_witness" in calls["purpose"]

    def test_module_has_no_hardcoded_ops_wt_path(self):
        """The ops-wt path must live in ONE place (engine/thetadata_store)."""
        from engine import theme_options_witness as mod
        assert not hasattr(mod, "_MAIN_CHECKOUT_THETA")
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "theta-ops-wt" not in src.replace(
            "engine.thetadata_store", ""), \
            "per-module hardcoded ops-wt fallback must be gone"

    def test_build_keeps_fresh_real_artifact_when_nothing_resolves(
            self, tmp_path, monkeypatch, isolated_chain):
        """End-to-end through the canonical resolver: NO tier resolves →
        _theta_store() is None → build() must leave the committed real
        artifact byte-identical (keep-last-real), never overwrite it with an
        all-suppressed output."""
        from engine import theme_options_witness as mod

        nw_out = tmp_path / "nw_out.json"
        site_out = tmp_path / "site_out.json"
        monkeypatch.setattr(mod, "_NW_OUT", nw_out)
        monkeypatch.setattr(mod, "_SITE_OUT", site_out)

        gen = datetime.now(tz=timezone.utc).isoformat()
        real = {
            "schema": "theme_options_witness.v1",
            "generated_at": gen,
            "coverage_stats": {"store_present": True, "n_themes": 18,
                               "n_themes_any_coverage": 18},
            "themes": {"T1": {"leg_a_call_oi_hhi": {"coverage_count": 5}}},
        }
        nw_out.write_text(json.dumps(real))
        site_out.write_text(json.dumps(real))
        before_nw = nw_out.read_text()
        before_site = site_out.read_text()

        # sanity: with every tier isolated to tmp, nothing resolves
        assert mod._theta_store() is None

        mod.build()

        assert nw_out.read_text() == before_nw, \
            "store-absent build must NOT clobber a fresh real NW artifact"
        assert site_out.read_text() == before_site, \
            "store-absent build must NOT clobber a fresh real site artifact"
