"""Tests for engine/crossasset_shadow.py — CA-W3-B shadow escalator.

Coverage:
  1. Escalation triggers only at pressure >= 0.90 AND incumbent >= "watch".
  2. Escalation cap: incumbent "elevated" + high pressure -> "risk-off" (max band).
  3. Incumbent at top band "risk-off" stays "risk-off" (cap at risk-off).
  4. Below-watch incumbents ("calm") NEVER escalate regardless of pressure.
  5. Missing pressure input -> None, no files written.
  6. Missing incumbent input -> None, no files written.
  7. Forward log appends only when lane armed (COLLECT_LANE=nightly).
  8. Dedup on asof: second call with same asof does not append a second row.
  9. latest.json schema: required keys present, display_only=True.
  10. Off-lane: returns result dict but writes nothing.

House law: tests never write real data/ (use tmp_path roots).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_regime(tmp_path: Path, absorption_pctile_5y=0.88, cross_asset: dict | None = None) -> None:
    """Write a minimal data/regime/latest.json under tmp_path."""
    ca_block = cross_asset if cross_asset is not None else {
        "asof":                 "2026-07-17",
        "absorption_pctile_5y": absorption_pctile_5y,
        "absorption_ratio":     0.42,
        "verdict":              "concentrated",
    }
    payload = {
        "asof":        "2026-07-17",
        "cross_asset": ca_block,
    }
    p = tmp_path / "data" / "regime"
    p.mkdir(parents=True, exist_ok=True)
    (p / "latest.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_fwd_log(tmp_path: Path, state: str = "caution", asof: str = "2026-07-17") -> None:
    """Write a minimal data/risk_radar/forward_log.jsonl under tmp_path."""
    p = tmp_path / "data" / "risk_radar"
    p.mkdir(parents=True, exist_ok=True)
    row = {"asof": asof, "state": state, "alert": False, "dominant_scare": "growth",
           "top_score": 60.0, "graded": None}
    (p / "forward_log.jsonl").write_text(
        json.dumps(row, separators=(",", ":")) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# TEST 1: Escalation at pressure >= 0.90 AND incumbent >= watch
# ---------------------------------------------------------------------------

def test_escalation_triggers_pressure_at_threshold(tmp_path, monkeypatch):
    """pressure=0.90 + incumbent='watch' -> shadow='caution', escalated=True."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    _write_regime(tmp_path, absorption_pctile_5y=0.90)
    _write_fwd_log(tmp_path, state="watch")

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))

    assert result is not None, "run() must return dict when inputs are present"
    assert result["shadow_state"] == "caution", (
        f"pressure=0.90 + watch -> shadow='caution'; got {result['shadow_state']!r}"
    )
    assert result["escalated"] is True
    assert result["incumbent_state"] == "watch"
    assert result["pressure_pctile"] == 0.90


def test_escalation_above_threshold(tmp_path, monkeypatch):
    """pressure=0.95 + incumbent='caution' -> shadow='elevated', escalated=True."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    _write_regime(tmp_path, absorption_pctile_5y=0.95)
    _write_fwd_log(tmp_path, state="caution")

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))

    assert result is not None
    assert result["shadow_state"] == "elevated"
    assert result["escalated"] is True


def test_no_escalation_below_threshold(tmp_path, monkeypatch):
    """pressure=0.89 (just below threshold) + incumbent='watch' -> no escalation."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    _write_regime(tmp_path, absorption_pctile_5y=0.89)
    _write_fwd_log(tmp_path, state="watch")

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))

    assert result is not None
    assert result["shadow_state"] == "watch", (
        f"pressure=0.89 < 0.90 -> no escalation; got {result['shadow_state']!r}"
    )
    assert result["escalated"] is False


# ---------------------------------------------------------------------------
# TEST 2: Escalation cap at risk-off
# ---------------------------------------------------------------------------

def test_escalation_cap_at_risk_off(tmp_path, monkeypatch):
    """pressure=0.99 + incumbent='elevated' -> shadow='risk-off' (capped, not beyond)."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    _write_regime(tmp_path, absorption_pctile_5y=0.99)
    _write_fwd_log(tmp_path, state="elevated")

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))

    assert result is not None
    assert result["shadow_state"] == "risk-off", (
        f"elevated+high pressure -> 'risk-off'; got {result['shadow_state']!r}"
    )
    assert result["escalated"] is True


# ---------------------------------------------------------------------------
# TEST 3: Incumbent at risk-off stays risk-off
# ---------------------------------------------------------------------------

def test_incumbent_risk_off_stays(tmp_path, monkeypatch):
    """pressure=0.99 + incumbent='risk-off' -> shadow='risk-off', escalated=False (already at cap)."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    _write_regime(tmp_path, absorption_pctile_5y=0.99)
    _write_fwd_log(tmp_path, state="risk-off")

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))

    assert result is not None
    assert result["shadow_state"] == "risk-off"
    # Already at top, so shadow == incumbent, escalated=False
    assert result["escalated"] is False


# ---------------------------------------------------------------------------
# TEST 4: Below-watch incumbents NEVER escalate
# ---------------------------------------------------------------------------

def test_calm_never_escalates(tmp_path, monkeypatch):
    """pressure=0.99 + incumbent='calm' -> shadow='calm', escalated=False.

    Below-watch incumbents are never escalated (CA-W3-R2: never a new origin scare).
    """
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    _write_regime(tmp_path, absorption_pctile_5y=0.99)
    _write_fwd_log(tmp_path, state="calm")

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))

    assert result is not None
    assert result["shadow_state"] == "calm", (
        f"below-watch 'calm' must never escalate; got {result['shadow_state']!r}"
    )
    assert result["escalated"] is False


# ---------------------------------------------------------------------------
# TEST 5: Missing pressure -> None, no files written
# ---------------------------------------------------------------------------

def test_missing_pressure_returns_none(tmp_path, monkeypatch):
    """regime/latest.json missing cross_asset block -> run() returns None, no writes."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _write_fwd_log(tmp_path, state="caution")

    # Write regime without cross_asset key
    p = tmp_path / "data" / "regime"
    p.mkdir(parents=True, exist_ok=True)
    (p / "latest.json").write_text(json.dumps({"asof": "2026-07-17"}), encoding="utf-8")

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))

    assert result is None, f"missing pressure -> None; got {result!r}"
    # No files should be written
    assert not (tmp_path / "data" / "crossasset_shadow" / "latest.json").exists()
    assert not (tmp_path / "data" / "risk_radar" / "forward_log_crossasset.jsonl").exists()


def test_missing_regime_file_returns_none(tmp_path, monkeypatch):
    """regime/latest.json absent -> run() returns None, no writes."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _write_fwd_log(tmp_path, state="caution")
    # regime/latest.json is NOT written

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))

    assert result is None


# ---------------------------------------------------------------------------
# TEST 6: Missing incumbent -> None, no files written
# ---------------------------------------------------------------------------

def test_missing_incumbent_returns_none(tmp_path, monkeypatch):
    """forward_log.jsonl absent -> run() returns None, no writes."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _write_regime(tmp_path, absorption_pctile_5y=0.95)
    # forward_log.jsonl is NOT written

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))

    assert result is None, f"missing incumbent -> None; got {result!r}"
    assert not (tmp_path / "data" / "crossasset_shadow" / "latest.json").exists()


def test_empty_fwd_log_returns_none(tmp_path, monkeypatch):
    """Empty forward_log.jsonl -> run() returns None."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _write_regime(tmp_path, absorption_pctile_5y=0.95)

    p = tmp_path / "data" / "risk_radar"
    p.mkdir(parents=True, exist_ok=True)
    (p / "forward_log.jsonl").write_text("", encoding="utf-8")

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))

    assert result is None


# ---------------------------------------------------------------------------
# TEST 7: Forward log appends only when lane armed
# ---------------------------------------------------------------------------

def test_forward_log_writes_when_armed(tmp_path, monkeypatch):
    """Lane armed (COLLECT_LANE=nightly) -> forward_log_crossasset.jsonl written."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _write_regime(tmp_path, absorption_pctile_5y=0.92)
    _write_fwd_log(tmp_path, state="watch")

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))

    assert result is not None
    fwd_path = tmp_path / "data" / "risk_radar" / "forward_log_crossasset.jsonl"
    assert fwd_path.exists(), "forward_log_crossasset.jsonl must be created when armed"
    rows = [json.loads(l) for l in fwd_path.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["market"] == "us"
    assert row["state"] == result["shadow_state"]
    assert row["incumbent_state"] == result["incumbent_state"]
    assert row["pressure_pct"] == result["pressure_pctile"]
    assert row["escalated"] is True   # pressure=0.92 + watch -> escalated


def test_forward_log_not_written_when_off_lane(tmp_path, monkeypatch):
    """Lane NOT armed -> forward_log_crossasset.jsonl must NOT be written."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    _write_regime(tmp_path, absorption_pctile_5y=0.92)
    _write_fwd_log(tmp_path, state="watch")

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))

    assert result is not None, "off-lane still returns result dict"
    fwd_path = tmp_path / "data" / "risk_radar" / "forward_log_crossasset.jsonl"
    assert not fwd_path.exists(), "forward log must NOT be written when lane is off"
    # latest.json also must not be written
    assert not (tmp_path / "data" / "crossasset_shadow" / "latest.json").exists()


# ---------------------------------------------------------------------------
# TEST 8: Dedup on asof
# ---------------------------------------------------------------------------

def test_dedup_on_asof(tmp_path, monkeypatch):
    """Second call with same asof does not append a second row to forward log."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _write_regime(tmp_path, absorption_pctile_5y=0.93)
    _write_fwd_log(tmp_path, state="caution", asof="2026-07-17")

    from engine import crossasset_shadow
    crossasset_shadow.run(root=str(tmp_path))  # first call
    crossasset_shadow.run(root=str(tmp_path))  # second call, same asof

    fwd_path = tmp_path / "data" / "risk_radar" / "forward_log_crossasset.jsonl"
    assert fwd_path.exists()
    rows = [json.loads(l) for l in fwd_path.read_text().splitlines() if l.strip()]
    assert len(rows) == 1, f"dedup must keep only 1 row per asof; got {len(rows)}"


# ---------------------------------------------------------------------------
# TEST 9: latest.json schema
# ---------------------------------------------------------------------------

def test_latest_json_schema(tmp_path, monkeypatch):
    """latest.json has all required keys and display_only=True."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _write_regime(tmp_path, absorption_pctile_5y=0.91)
    _write_fwd_log(tmp_path, state="watch", asof="2026-07-17")

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))
    assert result is not None

    latest_path = tmp_path / "data" / "crossasset_shadow" / "latest.json"
    assert latest_path.exists(), "latest.json must be written on armed lane"

    data = json.loads(latest_path.read_text(encoding="utf-8"))

    required_keys = {
        "asof", "market", "pressure_pctile", "incumbent_state",
        "shadow_state", "escalated", "display_only", "note", "built_at",
    }
    missing = required_keys - set(data.keys())
    assert not missing, f"latest.json missing keys: {missing}"

    assert data["display_only"] is True, "display_only must be True"
    assert data["market"] == "us", f"market must be 'us'; got {data['market']!r}"
    assert isinstance(data["escalated"], bool)
    assert isinstance(data["note"], str) and len(data["note"]) > 10
    assert data["shadow_state"] in ("calm", "watch", "caution", "elevated", "risk-off")
    assert data["incumbent_state"] in ("calm", "watch", "caution", "elevated", "risk-off")


# ---------------------------------------------------------------------------
# TEST 10: Off-lane: result returned, nothing written
# ---------------------------------------------------------------------------

def test_off_lane_result_not_none(tmp_path, monkeypatch):
    """Off-lane: result dict is returned (so callers can still use it in-memory)."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    _write_regime(tmp_path, absorption_pctile_5y=0.95)
    _write_fwd_log(tmp_path, state="caution")

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))

    assert result is not None
    assert set(result.keys()) == {"pressure_pctile", "incumbent_state", "shadow_state", "escalated"}


# ---------------------------------------------------------------------------
# TEST 11: Forward log row schema
# ---------------------------------------------------------------------------

def test_forward_log_row_schema(tmp_path, monkeypatch):
    """Forward log row matches CGL contagion shadow row schema (same grader compatibility)."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _write_regime(tmp_path, absorption_pctile_5y=0.92)
    _write_fwd_log(tmp_path, state="watch", asof="2026-07-17")

    from engine import crossasset_shadow
    crossasset_shadow.run(root=str(tmp_path))

    fwd_path = tmp_path / "data" / "risk_radar" / "forward_log_crossasset.jsonl"
    rows = [json.loads(l) for l in fwd_path.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    row = rows[0]

    # Schema must mirror CGL contagion shadow rows (so the same grader can mature them)
    required_fields = {
        "asof", "market", "state", "incumbent_state", "pressure_pct",
        "escalated", "top_score", "dominant_scare", "graded", "bench_path",
    }
    missing = required_fields - set(row.keys())
    assert not missing, f"forward log row missing fields: {missing}"

    assert row["graded"] is None, "new rows must have graded=None"
    assert row["market"] == "us"
    assert row["top_score"] is None
    assert row["bench_path"] is None
    assert isinstance(row["escalated"], bool)
    assert isinstance(row["dominant_scare"], str)


# ---------------------------------------------------------------------------
# TEST 12: absorption_pctile_5y absent (key present but null) -> None
# ---------------------------------------------------------------------------

def test_null_absorption_pctile_returns_none(tmp_path, monkeypatch):
    """absorption_pctile_5y = null in cross_asset -> run() returns None."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _write_fwd_log(tmp_path, state="caution")
    _write_regime(tmp_path, cross_asset={"asof": "2026-07-17", "absorption_pctile_5y": None})

    from engine import crossasset_shadow
    result = crossasset_shadow.run(root=str(tmp_path))

    assert result is None, f"null absorption_pctile_5y -> None; got {result!r}"
