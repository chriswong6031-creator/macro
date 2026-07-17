"""Lane gate for the market_state_tune mutating writers (port of the #2712
US audit gate; same class as the #2693 ignition gate).

House law: nightly is the SOLE advancer of data/ forward ledgers/overlays.
tune()'s call site (scripts/build_site.py market_state_view, right after
market_state_audit.snapshot_and_grade) also runs on closing-bell and the
engine-render/render re-render lanes with COLLECT_LANE unset — there tune()
must stay a pure read: the calibration overlay must not be written from a
mid-session store, and the tune_log / neuralweb-governance appends must not
produce PIT-inconsistent rows. Advancing lane verified via git log on
data/market_state/: every advancing commit is daily.yml engine job's
"engine: regime update" (job-level COLLECT_LANE=nightly); calibration.json
and tune_log.jsonl have no committed history yet (tune is still accruing —
this gate is preventive). Mirrors tests/test_us_audit_lane_gates.py.

NOTE tests/conftest.py arms COLLECT_LANE=nightly autouse — off-lane cases
must pop BOTH env vars explicitly.
"""
from __future__ import annotations

import json
from pathlib import Path

import engine.market_state as M
import engine.market_state_audit as A
import engine.market_state_tune as T
import engine.neuralweb.governance as G

ROOT = Path(__file__).resolve().parent.parent


def _row(asof, dd, keys, state="caution", sev=True, verdict="RISK_OFF", raw=61):
    return {"asof": asof, "verdict": verdict, "raw_score": raw, "radar_state": state,
            "amp": len(keys), "amp_keys": keys, "severe_gated": sev,
            "graded": {"any_dd5_within_h21": dd, "fwd_dd": {"h21": -0.06 if dd else 0.0}}}


def _seed(root, n_tp=12, n_fp=8, n_calm=5):
    """>= MIN_GRADED graded rows with clear signal so the first tune() applies."""
    rows = [_row(f"2026-02-{i+1:02d}", True, ["conjunction", "two_plus_scares", "complacency"])
            for i in range(n_tp)]
    rows += [_row(f"2026-03-{i+1:02d}", False, ["drawdown_band", "systemic_stress"])
             for i in range(n_fp)]
    rows += [_row(f"2026-04-{i+1:02d}", False, [], state="calm", sev=False, verdict="RISK_ON")
             for i in range(n_calm)]
    A._write(A._path(root), rows)


def _offlane(monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)


def _tune_log(root) -> Path:
    return Path(root) / "data" / "market_state" / "tune_log.jsonl"


def _gov_log(root) -> Path:
    return Path(root) / "data" / "neuralweb" / "governance.jsonl"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: the gate is the canonical #2712 one, not a drifted copy
# ═══════════════════════════════════════════════════════════════════════════

def test_gate_is_shared_with_market_state_audit():
    assert T.ledger_lane_armed is A.ledger_lane_armed, (
        "market_state_tune must reuse the canonical market_state_audit gate (#2712)"
    )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: off-lane tune() = pure read — display dict populated, zero writes
# ═══════════════════════════════════════════════════════════════════════════

def test_offlane_tune_is_readonly_but_returns_display(tmp_path, monkeypatch):
    _seed(tmp_path)
    calls = []
    monkeypatch.setattr(G, "append_event", lambda *a, **k: calls.append((a, k)) or True)

    _offlane(monkeypatch)
    r = T.tune(root=tmp_path)

    assert r["status"] in ("apply", "hold") and r["n_graded"] >= T.MIN_GRADED
    assert "weights" in r and "backtest" in r and "corr_lift" in r, (
        "display payload must stay populated off-lane"
    )
    assert "read-only lane" in r.get("note", ""), (
        "off-lane display dict must disclose that nothing was persisted"
    )
    assert not T._calib_path(tmp_path).exists() or \
        T._calib_path(tmp_path).read_text().strip() == "", (
        "off-lane tune must not write the calibration overlay"
    )
    assert not _tune_log(tmp_path).exists(), "off-lane tune must not append tune_log rows"
    assert calls == [], "off-lane tune must not append governance events"


def test_offlane_writers_noop_directly(tmp_path, monkeypatch):
    _offlane(monkeypatch)
    calib = {**M._ms_calib(root=tmp_path)}
    assert T._write_calib(tmp_path, calib, 0.5, 25) is False
    assert not T._calib_path(tmp_path).exists() or \
        T._calib_path(tmp_path).read_text().strip() == ""
    T._log_review(tmp_path, {"decision": "apply"})
    assert not _tune_log(tmp_path).exists()
    T._append_governance_a6(tmp_path, "apply", 25, 0.5, {"f1": 0.5}, {"f1": 0.6})
    assert not _gov_log(tmp_path).exists()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: on-lane tune() writes; an earlier off-lane call left nothing behind
# ═══════════════════════════════════════════════════════════════════════════

def test_offlane_then_nightly_writes_clean(tmp_path, monkeypatch):
    _seed(tmp_path)

    _offlane(monkeypatch)
    assert T.tune(root=tmp_path)["status"] in ("apply", "hold")

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    r = T.tune(root=tmp_path)
    assert r["status"] == "apply" and "note" not in r
    assert T._calib_path(tmp_path).exists(), "nightly apply must write the overlay"
    payload = json.loads(T._calib_path(tmp_path).read_text())
    assert payload["weights"] == r["weights"]
    rows = _tune_log(tmp_path).read_text().splitlines()
    assert len(rows) == 1, (
        "exactly one tune_log row — the off-lane call must not have contributed"
    )
    assert json.loads(rows[0])["decision"] == "apply"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: source tripwire — every mutating writer self-gates
# ═══════════════════════════════════════════════════════════════════════════

def test_tune_writers_self_gate_source():
    """Every mutating writer must check ledger_lane_armed() before touching
    disk (the closing-bell.yml contract: COLLECT_LANE is deliberately unset
    there BECAUSE every ledger writer self-gates)."""
    src = (ROOT / "engine" / "market_state_tune.py").read_text(encoding="utf-8")
    for fn in ("def _write_calib", "def _log_review", "def _append_governance_a6"):
        start = src.index(fn)
        nxt = src.find("\ndef ", start + 1)
        body = src[start: nxt if nxt != -1 else len(src)]
        assert "ledger_lane_armed()" in body, f"market_state_tune: {fn} is not lane-gated"
