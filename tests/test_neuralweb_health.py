"""tests/test_neuralweb_health.py — Unit tests for engine.neuralweb.health (PR-C).

Covers the full BUILD CONTRACT:
  1. Fresh artifact with n_rows
  2. Stale by SLA
  3. Missing (git-storage) vs not_locally_verifiable (r2-storage)
  4. Parquet row count via envelope sidecar (no pyarrow table load)
  5. Cortex degraded run_status → cortex section degraded + overall degraded
  6. Legacy memo without run_status still parses
  7. workflow_conformance flags a daily-engine producer absent from daily.yml
     (uses a tmp synapse fixture — does NOT depend on live repo state)
  8. --refresh-cortex preserves lobe sections, updates cortex + overall + produced_at
  9. site copy written alongside data copy
 10. per-lobe exception → status='unknown', not a raise
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import pytest

# --- repo root + import -------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.neuralweb.health import (  # noqa: E402
    build,
    refresh_cortex,
    write,
)


# ---- shared fixture helpers --------------------------------------------------

def _make_synapse_yaml(tmp_path: Path, artifacts: dict) -> Path:
    """Write a minimal synapse.yml with the given artifacts dict."""
    try:
        import yaml
    except ImportError:
        pytest.skip("pyyaml not installed")
    content = {"artifacts": artifacts}
    p = tmp_path / "config" / "synapse.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump(content, default_flow_style=False), encoding="utf-8")
    return p


def _make_repo(tmp_path: Path, artifacts: dict, daily_yml_text: str = "") -> Path:
    """
    Build a minimal fake repo under tmp_path:
      config/synapse.yml      — the given artifacts
      .github/workflows/daily.yml — the given text (empty = file absent)
    Returns the repo root.
    """
    _make_synapse_yaml(tmp_path, artifacts)
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    if daily_yml_text:
        (wf_dir / "daily.yml").write_text(daily_yml_text, encoding="utf-8")
    (tmp_path / "data" / "neuralweb" / "cortex").mkdir(parents=True, exist_ok=True)
    (tmp_path / "site" / "neuralwebdata").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _nw_json_artifact(tmp_path: Path, rel_path: str, payload: dict) -> Path:
    """Write a JSON artifact at rel_path under tmp_path."""
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(json.dumps(payload), encoding="utf-8")
    return full


def _art(
    path: str,
    *,
    format: str = "json",
    storage: str = "git",
    owner_program: str = "neural-web",
    cadence: str = "daily-engine",
    tier: str = "infrastructure",
    horizon_role: str = "context",
    freshness_sla_hours: float = 30.0,
    producer: str = "scripts/build_neuralweb_health.py",
    external_consumers: list | None = None,
) -> dict:
    return {
        "path": path,
        "format": format,
        "storage": storage,
        "owner_program": owner_program,
        "cadence": cadence,
        "tier": tier,
        "horizon_role": horizon_role,
        "freshness_sla_hours": freshness_sla_hours,
        "producer": producer,
        "known_extra_writers": [],
        "weights": "none",
        "scored_path_surfaces": [],
        "consumers": [],
        "external_consumers": external_consumers or [],
        "notes": "test fixture",
    }


# ---- test 1: fresh artifact with n_rows -------------------------------------

def test_fresh_artifact_with_nrows(tmp_path):
    """Fresh JSON artifact → status='fresh', row_count populated from content."""
    from datetime import datetime, timezone, timedelta
    # Use a timestamp 1 hour ago so it is always within the 30h SLA
    fresh_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    payload = {
        "as_of": fresh_ts,
        "produced_at": fresh_ts,
        "n_rows": 42,
    }
    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", payload)
    root = _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json", freshness_sla_hours=30.0),
    })
    result = build(root=root)
    lobes = {r["id"]: r for r in result["lobes"]}
    ws = lobes["world-state"]
    assert ws["status"] == "fresh", ws
    assert ws["row_count"] == 42
    assert ws["as_of"] == fresh_ts


# ---- test 2: stale by SLA ---------------------------------------------------

def test_stale_by_sla(tmp_path):
    """Artifact with as_of > SLA hours ago → status='stale'."""
    payload = {
        "as_of": "2020-01-01T00:00:00+00:00",  # very old
        "produced_at": "2020-01-01T00:00:00+00:00",
    }
    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", payload)
    root = _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json", freshness_sla_hours=30.0),
    })
    result = build(root=root)
    lobes = {r["id"]: r for r in result["lobes"]}
    assert lobes["world-state"]["status"] == "stale"


# ---- test 3a: missing (git-storage) -----------------------------------------

def test_missing_git_storage(tmp_path):
    """File does not exist and storage=git → status='missing'."""
    root = _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json", storage="git"),
    })
    # Do not create the file
    result = build(root=root)
    lobes = {r["id"]: r for r in result["lobes"]}
    assert lobes["world-state"]["status"] == "missing"


# ---- test 3b: not_locally_verifiable (r2-storage) ----------------------------

def test_not_locally_verifiable_r2_storage(tmp_path):
    """storage=r2 → status='not_locally_verifiable' even if file absent."""
    root = _make_repo(tmp_path, {
        "some-r2-artifact": _art("data/neuralweb/some_r2.json", storage="r2"),
    })
    result = build(root=root)
    lobes = {r["id"]: r for r in result["lobes"]}
    assert lobes["some-r2-artifact"]["status"] == "not_locally_verifiable"


# ---- test 4: parquet row count via envelope sidecar -------------------------

def test_parquet_count_via_envelope_sidecar(tmp_path):
    """Parquet artifact: row_count read from .envelope.json sidecar (no pyarrow table load)."""
    # Create a fake parquet file (content irrelevant — we read the sidecar)
    parquet_rel = "data/neuralweb/spine_index.parquet"
    full_parquet = tmp_path / parquet_rel
    full_parquet.parent.mkdir(parents=True, exist_ok=True)
    full_parquet.write_bytes(b"PAR1fake")  # not a real parquet
    sidecar = tmp_path / (parquet_rel + ".envelope.json")
    sidecar.write_text(json.dumps({
        "produced_at": "2026-07-06T00:00:00+00:00",
        "n_rows": 7777,
    }), encoding="utf-8")

    root = _make_repo(tmp_path, {
        "spine-index": _art(parquet_rel, format="parquet", storage="git"),
    })
    result = build(root=root)
    lobes = {r["id"]: r for r in result["lobes"]}
    spine = lobes["spine-index"]
    assert spine["row_count"] == 7777
    # Status should be fresh (sidecar provides a recent as_of)
    assert spine["status"] in ("fresh", "fresh_partial", "stale")


# ---- test 5: cortex degraded → overall degraded -----------------------------

def test_cortex_degraded_run_status_propagates(tmp_path):
    """Degraded run_status in cortex memo → cortex section degraded + overall degraded."""
    degraded_memo = {
        "schema": "neuralweb.cortex_memo.v1",
        "as_of": "2026-07-06T00:00:00+00:00",
        "summary": "budget exhausted",
        "what_fired": [],
        "run_status": {
            "status": "degraded",
            "degraded": True,
            "degradation_reason": "zero_tool_calls",
            "provider_attempts": [],
            "tool_call_batches": 0,
            "individual_tool_calls": 0,
            "expected_min_tool_calls": 1,
            "context_stale": False,
            "context_as_of": None,
        },
        "probation": {"granted": False, "reason": "n=0", "attention_track_record": {"n": 0, "hits": 0}},
    }
    (tmp_path / "data" / "neuralweb" / "cortex").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "neuralweb" / "cortex" / "memo.json").write_text(
        json.dumps(degraded_memo), encoding="utf-8"
    )
    # Also create a fresh world_state so degraded comes only from cortex
    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", {
        "as_of": "2026-07-06T00:00:00+00:00",
    })
    root = _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json"),
    })
    result = build(root=root)
    assert result["cortex"]["status"] == "degraded"
    assert result["overall_status"] == "degraded"


# ---- test 5b: model_fallback memo is warn, never fresh/ok -------------------

def test_cortex_model_fallback_is_warn_not_fresh(tmp_path):
    """Honesty law: a fallback-model run (degradation_reason='model_fallback') must produce
    cortex lobe status='warn' (not 'fresh') and overall_status != 'ok' in health.json.

    This guards against the regression where degraded=False (fallback ran tool calls) caused
    health.py to incorrectly surface the run as 'fresh', hiding the model substitution.
    """
    fallback_memo = {
        "schema": "neuralweb.cortex_memo.v1",
        "as_of": "2026-07-09T00:00:00+00:00",
        "summary": "fallback model summary",
        "what_fired": [],
        "run_status": {
            "status": "warn",
            "degraded": False,                      # fallback ran tool calls → not degraded
            "degradation_reason": "model_fallback", # but primary was rate-limited
            "model_used": "claude-sonnet-4-6",
            "provider_attempts": [],
            "tool_call_batches": 2,
            "individual_tool_calls": 5,
            "expected_min_tool_calls": 1,
            "context_stale": False,
            "context_as_of": None,
        },
        "probation": {"granted": False, "reason": "n=0", "attention_track_record": {"n": 0, "hits": 0}},
    }
    (tmp_path / "data" / "neuralweb" / "cortex").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "neuralweb" / "cortex" / "memo.json").write_text(
        json.dumps(fallback_memo), encoding="utf-8"
    )
    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", {
        "as_of": "2026-07-09T00:00:00+00:00",
    })
    root = _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json"),
    })
    result = build(root=root)
    cortex = result["cortex"]
    assert cortex["status"] == "warn", (
        f"model_fallback run must surface as cortex lobe 'warn', got {cortex['status']!r}. "
        "Honesty regression: degraded=False should not silently map to 'fresh' when "
        "degradation_reason='model_fallback'."
    )
    assert result["overall_status"] != "ok", (
        f"overall_status must not be 'ok' when cortex is 'warn' (model_fallback); "
        f"got {result['overall_status']!r}"
    )


# ---- test 6: legacy memo without run_status still parses --------------------

def test_legacy_memo_without_run_status(tmp_path):
    """Legacy memo without run_status field → derive from tool_call_census, no raise."""
    legacy_memo = {
        "schema": "neuralweb.cortex_memo.v1",
        "as_of": "2026-07-05T12:00:00+00:00",
        "summary": "legacy memo",
        "what_fired": ["signal_x"],
        "tool_call_census": {"read_world_state": 2},
        "probation": {"granted": False, "attention_track_record": {"n": 0, "hits": 0}},
        # No run_status key
    }
    (tmp_path / "data" / "neuralweb" / "cortex").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "neuralweb" / "cortex" / "memo.json").write_text(
        json.dumps(legacy_memo), encoding="utf-8"
    )
    root = _make_repo(tmp_path, {})
    # Must not raise
    result = build(root=root)
    cortex = result["cortex"]
    assert cortex["run_status"] is not None
    assert cortex["run_status"].get("_legacy_memo") is True
    # has_tools=True → legacy status is 'ok' (normal run, legacy format); lobe status 'fresh'
    assert cortex["run_status"].get("status") == "ok"
    assert cortex["status"] == "fresh"  # not degraded


# ---- test 7: workflow_conformance flags absent producer ---------------------

def test_workflow_conformance_flags_absent_producer(tmp_path):
    """daily-engine artifact whose producer is NOT in daily.yml → appears in misses."""
    # daily.yml text that does NOT mention the producer script at all
    # (use a name that has no overlap with the producer's stem)
    daily_text = "python -m scripts.build_world_state\npython -m scripts.build_spine_index\n"
    root = _make_repo(tmp_path, {
        "absent-lobe": _art(
            "data/neuralweb/absent_lobe.json",
            cadence="daily-engine",
            producer="scripts/build_absent_lobe_xyzzy.py",
        ),
    }, daily_yml_text=daily_text)
    _nw_json_artifact(tmp_path, "data/neuralweb/absent_lobe.json", {"as_of": "2026-07-06T00:00:00+00:00"})
    result = build(root=root)
    misses = result["workflow_conformance_misses"]
    assert any("build_absent_lobe_xyzzy" in (m.get("producer") or "") for m in misses), misses


def test_workflow_conformance_ok_when_producer_present(tmp_path):
    """Producer present in daily.yml → not flagged as a miss."""
    daily_text = "python -m scripts.build_neuralweb_health || echo warning"
    root = _make_repo(tmp_path, {
        "nw-health": _art("data/neuralweb/health.json", cadence="daily-engine",
                          producer="scripts/build_neuralweb_health.py"),
    }, daily_yml_text=daily_text)
    _nw_json_artifact(tmp_path, "data/neuralweb/health.json", {"as_of": "2026-07-06T00:00:00+00:00"})
    result = build(root=root)
    misses = result["workflow_conformance_misses"]
    assert not any("build_neuralweb_health" in (m.get("producer") or "") for m in misses), misses


# ---- test 8: --refresh-cortex preserves lobes, updates cortex --------------

def test_refresh_cortex_preserves_lobes_updates_cortex(tmp_path):
    """refresh_cortex() preserves lobe sections and updates cortex + overall + produced_at."""
    import time as _time
    from datetime import datetime, timezone, timedelta

    # Use a fresh timestamp so the SLA check always passes
    fresh_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    fresh_ts2 = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # Build an initial artifact
    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", {
        "as_of": fresh_ts,
    })
    root = _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json"),
    })
    first = build(root=root, cortex_source="previous_run")
    assert first["cortex"]["cortex_source"] == "previous_run"
    first_produced = first["produced_at"]

    # Small sleep to ensure produced_at changes
    _time.sleep(0.05)

    # Write a cortex memo with ok status
    ok_memo = {
        "as_of": fresh_ts2,
        "run_status": {
            "status": "ok",
            "degraded": False,
            "degradation_reason": None,
            "tool_call_batches": 3,
            "individual_tool_calls": 9,
            "expected_min_tool_calls": 1,
            "context_stale": False,
            "context_as_of": None,
        },
    }
    (tmp_path / "data" / "neuralweb" / "cortex" / "memo.json").write_text(
        json.dumps(ok_memo), encoding="utf-8"
    )

    second = refresh_cortex(first, root=root)

    # Lobes preserved
    assert second["lobes"] == first["lobes"]
    # Cortex source updated
    assert second["cortex"]["cortex_source"] == "current_run"
    # produced_at updated
    assert second["produced_at"] >= first_produced
    # overall_status — cortex now ok, world-state fresh → ok
    assert second["overall_status"] in ("ok", "warn")


# ---- test 9: site copy written alongside data copy --------------------------

def test_write_produces_both_copies(tmp_path):
    """write() creates both data/neuralweb/health.json and site/neuralwebdata/health.json."""
    payload = {
        "schema": "neuralweb.health.v1",
        "produced_at": "2026-07-06T00:00:00+00:00",
        "overall_status": "ok",
        "lobes": [],
    }
    (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
    (tmp_path / "site" / "neuralwebdata").mkdir(parents=True, exist_ok=True)
    write(payload, root=tmp_path)
    data_path = tmp_path / "data" / "neuralweb" / "health.json"
    site_path = tmp_path / "site" / "neuralwebdata" / "health.json"
    assert data_path.exists()
    assert site_path.exists()
    assert json.loads(data_path.read_text()) == payload
    assert json.loads(site_path.read_text()) == payload


# ---- test 10: per-lobe exception → unknown not raise ------------------------

def test_per_lobe_exception_returns_unknown(tmp_path, monkeypatch):
    """If a lobe's record function raises unexpectedly, status='unknown'; build does not raise."""
    # Create a valid synapse entry pointing to a json file
    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", {
        "as_of": "2026-07-06T00:00:00+00:00",
    })
    root = _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json"),
    })

    # Monkeypatch _lobe_record to raise for this specific id
    import engine.neuralweb.health as _health
    original = _health._lobe_record

    def _raise_lobe(art_id, art, r):
        if art_id == "world-state":
            raise RuntimeError("injected failure")
        return original(art_id, art, r)

    monkeypatch.setattr(_health, "_lobe_record", _raise_lobe)
    result = build(root=root)
    lobes = {r["id"]: r for r in result["lobes"]}
    assert lobes["world-state"]["status"] == "unknown"
    assert any("injected failure" in str(g) for g in lobes["world-state"]["gaps"])


# ---- test: scope selection ---------------------------------------------------

def test_scope_includes_mastermind_context_external_consumer(tmp_path):
    """Artifacts with external_consumers=['mastermind:context'] are included in scope."""
    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", {
        "as_of": "2026-07-06T00:00:00+00:00",
    })
    root = _make_repo(tmp_path, {
        "world-state": _art(
            "data/neuralweb/world_state.json",
            owner_program="some-other-program",  # not neural-web
            external_consumers=["mastermind:context"],
        ),
    })
    result = build(root=root)
    lobe_ids = [r["id"] for r in result["lobes"]]
    assert "world-state" in lobe_ids


def test_scope_excludes_non_nw_artifacts(tmp_path):
    """Artifacts outside NW scope are not included in health lobes."""
    _nw_json_artifact(tmp_path, "data/some_other/thing.json", {
        "as_of": "2026-07-06T00:00:00+00:00",
    })
    root = _make_repo(tmp_path, {
        "non-nw-artifact": _art(
            "data/some_other/thing.json",
            owner_program="oracle",
            external_consumers=[],
        ),
    })
    result = build(root=root)
    lobe_ids = [r["id"] for r in result["lobes"]]
    assert "non-nw-artifact" not in lobe_ids


# ---- test: missing synapse.yml → skeleton, exit 0 -------------------------

def test_missing_synapse_yml_returns_skeleton(tmp_path):
    """Missing synapse.yml → build returns a skeleton dict, does not raise."""
    # No synapse.yml in this tmp_path
    (tmp_path / "data" / "neuralweb" / "cortex").mkdir(parents=True, exist_ok=True)
    (tmp_path / "site" / "neuralwebdata").mkdir(parents=True, exist_ok=True)
    result = build(root=tmp_path)
    assert result["schema"] == "neuralweb.health.v1"
    assert result["lobes"] == []
    assert result["overall_status"] == "unknown"


# ---- test: build_neuralweb_health CLI ---------------------------------------

def test_cli_full_build_writes_both_copies(tmp_path):
    """CLI full build mode writes both data/ and site/ copies."""
    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", {
        "as_of": "2026-07-06T00:00:00+00:00",
    })
    _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json"),
    })

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_neuralweb_health",
        _REPO_ROOT / "scripts" / "build_neuralweb_health.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    rc = mod.main(["--root", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "data" / "neuralweb" / "health.json").exists()
    assert (tmp_path / "site" / "neuralwebdata" / "health.json").exists()


def test_cli_refresh_cortex_preserves_lobes(tmp_path):
    """CLI --refresh-cortex preserves lobe records and sets cortex_source=current_run."""
    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", {
        "as_of": "2026-07-06T00:00:00+00:00",
    })
    _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json"),
    })

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_neuralweb_health",
        _REPO_ROOT / "scripts" / "build_neuralweb_health.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Full build first
    rc = mod.main(["--root", str(tmp_path)])
    assert rc == 0

    first = json.loads((tmp_path / "data" / "neuralweb" / "health.json").read_text())
    assert first["cortex"]["cortex_source"] == "previous_run"

    # Write a cortex memo
    ok_memo = {
        "as_of": "2026-07-06T01:00:00+00:00",
        "run_status": {
            "status": "ok", "degraded": False, "degradation_reason": None,
            "tool_call_batches": 2, "individual_tool_calls": 4,
            "expected_min_tool_calls": 1, "context_stale": False, "context_as_of": None,
        },
    }
    (tmp_path / "data" / "neuralweb" / "cortex" / "memo.json").write_text(
        json.dumps(ok_memo), encoding="utf-8"
    )

    rc2 = mod.main(["--root", str(tmp_path), "--refresh-cortex"])
    assert rc2 == 0

    second = json.loads((tmp_path / "data" / "neuralweb" / "health.json").read_text())
    assert second["cortex"]["cortex_source"] == "current_run"
    # Lobes unchanged
    assert second["lobes"] == first["lobes"]


# ---------------------------------------------------------------------------
# Date-pin regression tests (2026-07-02 as_of fixed-point incident)
# ---------------------------------------------------------------------------

def test_iso_hours_ago_parses_naive_and_date_only():
    """REGRESSION: date-only and naive ISO strings must parse (coerced to UTC),
    not TypeError→None.  The silent None sent every date-only lobe to the mtime
    fallback, which pinned health as_of at 2026-07-02 forever."""
    from engine.neuralweb.health import _iso_hours_ago

    # date-only string → midnight UTC; well in the past → large positive age
    h = _iso_hours_ago("2020-01-01")
    assert h is not None, "date-only as_of must not fall back to None"
    assert h > 24 * 365  # years old

    # naive full timestamp → coerced to UTC
    h2 = _iso_hours_ago("2020-01-01T05:00:00")
    assert h2 is not None
    assert h2 == pytest.approx(h - 5, abs=0.1)

    # aware timestamps still work; junk still returns None
    assert _iso_hours_ago("2020-01-01T00:00:00+00:00") == pytest.approx(h, abs=0.1)
    assert _iso_hours_ago("not-a-date") is None
    assert _iso_hours_ago(None) is None


def test_date_only_old_as_of_is_stale_despite_fresh_mtime(tmp_path):
    """REGRESSION: a freshly-written file whose CONTENT as_of is an old date-only
    string must count 'stale' — before the fix the naive-datetime TypeError made
    the age fall back to file mtime, so self-monitoring lobes always counted
    'fresh' while carrying as_of='2026-07-02'."""
    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", {
        "as_of": "2020-01-01",  # date-only, ancient — but the file mtime is NOW
    })
    root = _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json", freshness_sla_hours=30.0),
    })
    result = build(root=root)
    lobes = {r["id"]: r for r in result["lobes"]}
    ws = lobes["world-state"]
    assert ws["status"] == "stale", ws
    assert ws["age_hours"] is not None and ws["age_hours"] > 30.0


def test_self_monitor_lobes_excluded_from_as_of_rollup(tmp_path):
    """REGRESSION: health/daily-brief artifacts (self-monitoring lobes) must NOT
    feed the as_of min rollup — their as_of IS the previous rollup, so including
    them re-ingests the old minimum forever (the date-pin fixed point)."""
    from datetime import datetime, timezone, timedelta

    fmt = "%Y-%m-%dT%H:%M:%S+00:00"
    ws_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(fmt)
    # Older but still within the 30h SLA → the self lobes stay 'fresh', so only
    # the path-based exclusion (not the status filter) keeps them out of the min.
    pinned_ts = (datetime.now(timezone.utc) - timedelta(hours=10)).strftime(fmt)

    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", {"as_of": ws_ts})
    _nw_json_artifact(tmp_path, "data/neuralweb/health.json", {"as_of": pinned_ts})
    _nw_json_artifact(tmp_path, "site/neuralwebdata/health.json", {"as_of": pinned_ts})
    _nw_json_artifact(tmp_path, "data/neuralweb/daily_brief.json", {"as_of": pinned_ts})
    _nw_json_artifact(tmp_path, "site/neuralwebdata/daily_brief.json", {"as_of": pinned_ts})

    root = _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json"),
        "neuralweb-health": _art("data/neuralweb/health.json"),
        "site-neuralweb-health": _art("site/neuralwebdata/health.json"),
        "neuralweb-daily-brief": _art("data/neuralweb/daily_brief.json"),
        "site-neuralweb-daily-brief": _art("site/neuralwebdata/daily_brief.json"),
    })
    result = build(root=root)

    lobes = {r["id"]: r for r in result["lobes"]}
    # The self lobes ARE fresh (10h < 30h SLA) — they are excluded by path only
    assert lobes["neuralweb-health"]["status"] == "fresh"
    assert lobes["site-neuralweb-daily-brief"]["status"] == "fresh"
    # ...but the rollup ignores them and resolves to the real data timestamp
    assert result["as_of"] == ws_ts, (
        f"as_of must come from world-state ({ws_ts}), not the self-monitoring "
        f"lobes' pinned {pinned_ts}; got {result['as_of']}"
    )


def test_self_monitor_lobe_age_anchors_on_produced_at(tmp_path):
    """A self-monitoring lobe's as_of is a conservative rollup (legitimately
    old); its freshness anchor is produced_at.  Recent produced_at → fresh even
    with a >SLA-old rollup as_of; old produced_at → honestly stale."""
    from datetime import datetime, timezone, timedelta

    fmt = "%Y-%m-%dT%H:%M:%S+00:00"
    recent_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime(fmt)

    # Monitor ran 2h ago but its conservative rollup as_of is 50h old
    _nw_json_artifact(tmp_path, "data/neuralweb/health.json", {
        "as_of": (datetime.now(timezone.utc) - timedelta(hours=50)).strftime(fmt),
        "produced_at": recent_ts,
    })
    # Monitor did NOT run: produced_at is 50h old too
    _nw_json_artifact(tmp_path, "data/neuralweb/daily_brief.json", {
        "as_of": (datetime.now(timezone.utc) - timedelta(hours=50)).strftime(fmt),
        "produced_at": (datetime.now(timezone.utc) - timedelta(hours=50)).strftime(fmt),
    })
    root = _make_repo(tmp_path, {
        "neuralweb-health": _art("data/neuralweb/health.json", freshness_sla_hours=30.0),
        "neuralweb-daily-brief": _art("data/neuralweb/daily_brief.json", freshness_sla_hours=30.0),
    })
    result = build(root=root)
    lobes = {r["id"]: r for r in result["lobes"]}
    assert lobes["neuralweb-health"]["status"] == "fresh", lobes["neuralweb-health"]
    assert lobes["neuralweb-daily-brief"]["status"] == "stale", lobes["neuralweb-daily-brief"]


# ---------------------------------------------------------------------------
# W1 test: context_accrual heartbeat (R-CI12)
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_w1_context_accrual_heartbeat_in_build_output(tmp_path: Path) -> None:
    """W1 R-CI12: build() includes 'context_accrual' block with the three sub-blocks.

    Tests fail-open: all sub-blocks present even when files are absent.
    Also tests that fire_coordinates rows are read correctly when the file exists.
    """
    from engine.neuralweb.health import build, write, _context_accrual_heartbeat

    # Write minimal synapse.yml so build() doesn't skip to skeleton
    _make_synapse_yaml(tmp_path, {})  # empty artifacts — that's fine for this test

    # Write a cortex memo so build() is happy
    (tmp_path / "data" / "neuralweb" / "cortex").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "neuralweb" / "cortex" / "memo.json").write_text(
        json.dumps({"as_of": "2026-07-06", "run_status": {"status": "ok"}}),
        encoding="utf-8"
    )

    payload = build(root=tmp_path, cortex_source="previous_run")

    # context_accrual block must be present
    assert "context_accrual" in payload, "R-CI12: context_accrual block missing from build() output"
    ca = payload["context_accrual"]

    # Sub-blocks present (fail-open: files absent on CI → exists=False, not an error)
    assert "personality_forward_ledger" in ca
    assert "fire_coordinates" in ca
    assert "panel_partitions" in ca
    assert "stamper_gap" in ca

    # personality_forward_ledger: exists=False (no file in tmp_path)
    fl = ca["personality_forward_ledger"]
    assert fl["exists"] is False
    assert fl["rows"] is None

    # panel_partitions: n=0 (no panel in tmp_path)
    pp = ca["panel_partitions"]
    assert pp["n"] == 0
    assert pp["latest"] is None


def test_w1_context_accrual_heartbeat_with_fire_coords(tmp_path: Path) -> None:
    """W1 R-CI12: when fire_coordinates.jsonl exists, the heartbeat reports
    rows, last_asof, and dna_nonnull_pct correctly.
    """
    from engine.neuralweb.health import _context_accrual_heartbeat

    # Write synthetic fire_coordinates.jsonl
    fc_rows = [
        {"as_of": "2026-07-04", "ticker": "AAPL", "dna_class": "quality_growth",
         "fire_coord_schema": "fire_coordinates.v2"},
        {"as_of": "2026-07-05", "ticker": "MSFT", "dna_class": None,
         "fire_coord_schema": "fire_coordinates.v2"},
        {"as_of": "2026-07-06", "ticker": "GOOGL", "dna_class": "momentum_leader",
         "fire_coord_schema": "fire_coordinates.v2"},
    ]
    _write_jsonl(tmp_path / "data" / "factordata" / "fire_coordinates.jsonl", fc_rows)

    result = _context_accrual_heartbeat(tmp_path)

    fc = result["fire_coordinates"]
    assert fc["exists"] is True
    assert fc["rows"] == 3
    assert fc["last_asof"] == "2026-07-06"
    # 2 of 3 rows have non-null dna_class
    assert fc["dna_nonnull_pct"] == pytest.approx(66.7, abs=0.1)


def test_w1_context_accrual_heartbeat_stamper_gap(tmp_path: Path) -> None:
    """W1 R-CI12: stamper_gap=True when track_record has buy fires on dates
    AT OR AFTER the ledger wire_floor that are NOT present in the forward_ledger.

    Wire-floor rule: the ledger's earliest date is the wire_floor.  Fires BEFORE
    the wire_floor are historical pre-wire fires and must NOT flag (tested in the
    regression test below).  Only post-wire fires trigger stamper_gap.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq
    from engine.neuralweb.health import _context_accrual_heartbeat

    # Forward_ledger established (wired) on 2026-07-01.
    # wire_floor = "2026-07-01" (min of ledger dates).
    fl_path = tmp_path / "data" / "stock_personality" / "forward_ledger.parquet"
    fl_path.parent.mkdir(parents=True, exist_ok=True)
    fl_df = pa.table({
        "as_of": pa.array(["2026-07-01"], type=pa.string()),
    })
    pq.write_table(fl_df, str(fl_path))

    # track_record has a buy fire on 2026-07-02 (AFTER wire_floor=2026-07-01).
    # The ledger only covers 2026-07-01 → gap on 2026-07-02.
    tr_path = tmp_path / "data" / "signal_archive" / "track_record.parquet"
    tr_path.parent.mkdir(parents=True, exist_ok=True)
    tr_df = pa.table({
        "date": pa.array(["2026-07-02", "2026-07-02"], type=pa.string()),
        "type": pa.array(["buy", "rebuy"], type=pa.string()),
    })
    pq.write_table(tr_df, str(tr_path))

    result = _context_accrual_heartbeat(tmp_path)

    # 2026-07-02 is post-wire and NOT in forward_ledger → stamper_gap=True
    assert result["stamper_gap"] is True, (
        f"expected stamper_gap=True for post-wire miss, got {result['stamper_gap']}. Full: {result}"
    )
    assert "stamper_gap_dates_sample" in result
    assert "2026-07-02" in result["stamper_gap_dates_sample"]

    # Add 2026-07-02 to the ledger → stamper_gap should resolve to False
    fl_df2 = pa.table({
        "as_of": pa.array(["2026-07-01", "2026-07-02"], type=pa.string()),
    })
    pq.write_table(fl_df2, str(fl_path))

    result2 = _context_accrual_heartbeat(tmp_path)
    assert result2["stamper_gap"] is False, (
        f"expected stamper_gap=False after ledger covers the gap date, got {result2['stamper_gap']}"
    )


def test_w1_stamper_gap_pre_wire_fires_do_not_flag(tmp_path: Path) -> None:
    """W1 R-CI12 false-positive regression: buy fires BEFORE the ledger wire_floor
    must NOT set stamper_gap=True.

    Scenario: ledger wire_floor = 2026-07-05 (ledger's earliest entry).
    track_record has historical buy fires on 2026-06-01 (pre-wire).
    These fires pre-date the ledger; the stamper could not have run then.
    Expected: stamper_gap=False (no false alarm).
    """
    import pyarrow as pa
    import pyarrow.parquet as pq
    from engine.neuralweb.health import _context_accrual_heartbeat

    # Ledger wired on 2026-07-05 — wire_floor = "2026-07-05"
    fl_path = tmp_path / "data" / "stock_personality" / "forward_ledger.parquet"
    fl_path.parent.mkdir(parents=True, exist_ok=True)
    fl_df = pa.table({
        "as_of": pa.array(["2026-07-05", "2026-07-06"], type=pa.string()),
    })
    pq.write_table(fl_df, str(fl_path))

    # track_record has buy fires ONLY on 2026-06-01 (well before wire_floor)
    tr_path = tmp_path / "data" / "signal_archive" / "track_record.parquet"
    tr_path.parent.mkdir(parents=True, exist_ok=True)
    tr_df = pa.table({
        "date": pa.array(["2026-06-01", "2026-06-15"], type=pa.string()),
        "type": pa.array(["buy", "buy"], type=pa.string()),
    })
    pq.write_table(tr_df, str(tr_path))

    result = _context_accrual_heartbeat(tmp_path)

    # Pre-wire fires must NOT flag — this is the false-positive regression
    assert result["stamper_gap"] is False, (
        f"FALSE POSITIVE: historical pre-wire fires flagged stamper_gap=True. "
        f"wire_floor should exclude 2026-06-01 fires. Full result: {result}"
    )
    # fires_seen_since_wire should be 0 (no fires after wire_floor)
    assert result.get("fires_seen_since_wire") == 0, (
        f"expected fires_seen_since_wire=0 (all fires pre-wire), got "
        f"{result.get('fires_seen_since_wire')}"
    )


# ---------------------------------------------------------------------------
# CHANGE 1: weekend-aware staleness threshold
# ---------------------------------------------------------------------------

def test_friday_asof_not_stale_on_saturday(tmp_path, monkeypatch):
    """CHANGE 1: a Friday as_of must NOT be stale on Saturday or Sunday
    (within the 30h SLA window when measured from the following Monday).

    Time is frozen at Saturday 06:00 UTC — 30 hours after Friday midnight
    (wall-clock) but only 6 hours after the following Monday 00:00 base.
    Without weekend-awareness the Friday artifact would be stale (30h > 30h SLA).
    With weekend-awareness the clock starts at Monday 00:00 → 6h → fresh.
    """
    from datetime import datetime, timezone, timedelta
    import engine.neuralweb.health as _health

    # Find the most recent Friday relative to an arbitrary anchor
    # Anchor: pick a known Friday date
    friday_date = "2026-07-10"  # 2026-07-10 is a Friday

    payload = {
        "as_of": friday_date,
        "produced_at": friday_date + "T00:00:00+00:00",
        "n_rows": 1,
    }
    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", payload)
    root = _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json", freshness_sla_hours=30.0),
    })

    # Freeze time to Saturday 2026-07-11 06:00 UTC.
    # Wall-clock age = (Sat 06:00 - Fri 00:00) = 30h → would be stale without fix.
    # Weekend-aware base = Monday 2026-07-13 00:00 UTC; (Sat 06:00 - Mon 00:00) < 0
    # (now is BEFORE the base) → age_hours negative → not stale.
    frozen_now = datetime(2026, 7, 11, 6, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(_health, "_iso_hours_ago", lambda ts: (
        (frozen_now - datetime.fromisoformat(
            (ts or "").replace("Z", "+00:00")
        ).replace(tzinfo=timezone.utc)).total_seconds() / 3600
        if ts else None
    ))

    original_is_stale = _health._is_stale_weekend_aware

    def _frozen_is_stale(as_of_str, sla_hours, now=None):
        return original_is_stale(as_of_str, sla_hours, now=frozen_now)

    monkeypatch.setattr(_health, "_is_stale_weekend_aware", _frozen_is_stale)

    result = build(root=root)
    lobes = {r["id"]: r for r in result["lobes"]}
    ws = lobes["world-state"]
    assert ws["status"] == "fresh", (
        f"Friday as_of must be fresh on Saturday (weekend-aware): got {ws['status']!r}. "
        f"age_hours={ws.get('age_hours')}"
    )


def test_friday_asof_stale_after_monday_sla(tmp_path, monkeypatch):
    """CHANGE 1: Friday as_of must become stale if now > Monday + SLA."""
    from datetime import datetime, timezone
    import engine.neuralweb.health as _health

    friday_date = "2026-07-10"
    payload = {"as_of": friday_date, "produced_at": friday_date + "T00:00:00+00:00"}
    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", payload)
    root = _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json", freshness_sla_hours=30.0),
    })

    # Freeze time to Wednesday 2026-07-15 10:00 UTC.
    # Monday base = 2026-07-13 00:00; elapsed = 58h > 30h SLA → stale.
    frozen_now = datetime(2026, 7, 15, 10, 0, 0, tzinfo=timezone.utc)

    original_is_stale = _health._is_stale_weekend_aware

    def _frozen_is_stale(as_of_str, sla_hours, now=None):
        return original_is_stale(as_of_str, sla_hours, now=frozen_now)

    monkeypatch.setattr(_health, "_is_stale_weekend_aware", _frozen_is_stale)

    result = build(root=root)
    lobes = {r["id"]: r for r in result["lobes"]}
    ws = lobes["world-state"]
    assert ws["status"] == "stale", (
        f"Friday as_of must be stale on Wednesday (beyond SLA from Monday): "
        f"got {ws['status']!r}"
    )


# ---------------------------------------------------------------------------
# CHANGE 2: collect-cadence exclusion from as_of rollup
# ---------------------------------------------------------------------------

def test_collect_cadence_excluded_from_asof_rollup(tmp_path):
    """CHANGE 2: lobes with cadence='collect' must not pin the top-level as_of.

    Collect-cadence artifacts are written once (offline) and never advanced by
    the nightly pipeline; including them would pin as_of to their one-time build
    date forever.
    """
    from datetime import datetime, timezone, timedelta

    fmt = "%Y-%m-%dT%H:%M:%S+00:00"
    ws_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime(fmt)
    # Collect artifact pinned to 2026-07-09 (very old relative to ws_ts)
    collect_ts = "2026-07-09T00:00:00+00:00"

    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", {"as_of": ws_ts})
    # Collect artifact freshness_sla_hours=2160 → within SLA (still 'fresh')
    _nw_json_artifact(tmp_path, "data/neuralweb/discovery_confluence.json", {
        "as_of": collect_ts,
        "produced_at": collect_ts,
    })
    root = _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json", freshness_sla_hours=30.0),
        "neuralweb-discovery-confluence": _art(
            "data/neuralweb/discovery_confluence.json",
            cadence="collect",
            freshness_sla_hours=2160.0,
        ),
    })
    result = build(root=root)
    assert result["as_of"] == ws_ts, (
        f"collect-cadence lobe must not pin as_of; expected {ws_ts!r}, got {result['as_of']!r}"
    )


# ---------------------------------------------------------------------------
# CHANGE 3a: staleness_from override
# ---------------------------------------------------------------------------

def test_staleness_from_produced_at_overrides_event_asof(tmp_path, monkeypatch):
    """CHANGE 3a: when staleness_from='produced_at' is set in the synapse entry,
    the staleness comparison uses produced_at (nightly) not as_of (event date).

    Scenario: confluence-strength whose content as_of = old event date (2026-07-02)
    but produced_at = recent (1 hour ago). Without staleness_from the lobe would
    be stale because 2026-07-02 > 30h SLA. With staleness_from=produced_at it
    is fresh because produced_at < 30h.
    """
    from datetime import datetime, timezone, timedelta

    fmt = "%Y-%m-%dT%H:%M:%S+00:00"
    recent_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(fmt)
    old_event_ts = "2026-07-02T00:00:00+00:00"  # ancient — would fail 30h SLA

    _nw_json_artifact(tmp_path, "data/neuralweb/confluence_strength.json", {
        "as_of": old_event_ts,        # event date — displayed but NOT used for staleness
        "produced_at": recent_ts,     # nightly run — used for staleness
        "schema": "neuralweb.confluence_strength.v1",
    })
    # Build the fake world-state so there's a fresh non-collect anchor for as_of rollup
    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", {"as_of": recent_ts})
    art_def = _art(
        "data/neuralweb/confluence_strength.json",
        freshness_sla_hours=30.0,
    )
    art_def["staleness_from"] = "produced_at"
    root = _make_repo(tmp_path, {
        "confluence-strength": art_def,
        "world-state": _art("data/neuralweb/world_state.json", freshness_sla_hours=30.0),
    })
    result = build(root=root)
    lobes = {r["id"]: r for r in result["lobes"]}
    cs = lobes["confluence-strength"]
    # as_of display must still be the event date
    assert cs["as_of"] == old_event_ts, (
        f"as_of display must remain the event date; got {cs['as_of']!r}"
    )
    # Status must be fresh (produced_at is recent)
    assert cs["status"] == "fresh", (
        f"staleness_from=produced_at must yield fresh when produced_at < SLA; "
        f"got {cs['status']!r}"
    )


# ---------------------------------------------------------------------------
# CHANGE 3b: missing-placeholder rollup
# ---------------------------------------------------------------------------

def test_missing_placeholder_sla_9999_not_degraded(tmp_path):
    """CHANGE 3b: a missing lobe with freshness_sla_hours=9999 (placeholder,
    never-built) must NOT drive overall_status to 'degraded'.
    Per-lobe status stays 'missing' (nulls printed, not hidden).
    """
    from datetime import datetime, timezone, timedelta

    fmt = "%Y-%m-%dT%H:%M:%S+00:00"
    fresh_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(fmt)

    # world-state: fresh (exists)
    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", {"as_of": fresh_ts})
    # placeholder lobe: does NOT exist on disk; sla=9999
    root = _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json", freshness_sla_hours=30.0),
        "placeholder-lobe": _art(
            "data/neuralweb/placeholder.json",
            freshness_sla_hours=9999.0,
        ),
    })
    result = build(root=root)
    lobes = {r["id"]: r for r in result["lobes"]}

    # Per-lobe status must still be 'missing' (honesty)
    assert lobes["placeholder-lobe"]["status"] == "missing", (
        f"per-lobe status must be 'missing' regardless of SLA; got "
        f"{lobes['placeholder-lobe']['status']!r}"
    )
    # But overall must NOT be 'degraded' because of this placeholder
    assert result["overall_status"] != "degraded", (
        f"SLA=9999 missing placeholder must not drive overall_status to 'degraded'; "
        f"got {result['overall_status']!r}"
    )


def test_missing_sla_30_drives_degraded(tmp_path):
    """CHANGE 3b: a missing lobe with real SLA=30 (expected nightly artifact)
    must still drive overall_status to 'degraded'.
    """
    from datetime import datetime, timezone, timedelta

    fmt = "%Y-%m-%dT%H:%M:%S+00:00"
    fresh_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(fmt)

    _nw_json_artifact(tmp_path, "data/neuralweb/world_state.json", {"as_of": fresh_ts})
    # factor-contradictions-ledger analog: SLA=30, actually expected, absent → degraded
    root = _make_repo(tmp_path, {
        "world-state": _art("data/neuralweb/world_state.json", freshness_sla_hours=30.0),
        "expected-lobe": _art(
            "data/neuralweb/expected_lobe.json",
            freshness_sla_hours=30.0,
        ),
    })
    # Do NOT create expected_lobe.json
    result = build(root=root)
    lobes = {r["id"]: r for r in result["lobes"]}

    assert lobes["expected-lobe"]["status"] == "missing"
    assert result["overall_status"] == "degraded", (
        f"SLA=30 missing lobe must drive overall_status to 'degraded'; "
        f"got {result['overall_status']!r}"
    )
