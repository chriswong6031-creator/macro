"""Publication-path regression tests for the macro workspace builder (F01 / R1A).

Adversarial review round 1, finding F5: exercise ``engine.market_os.macro_workspaces.build``
end-to-end into a tmp dir, and the CLI's exit-code contract (finding F4). Also
carries F2's determinism-under-code_version-churn test (F2's own fix lives in
``contract.py``; this is the publish-path proof of it).

    python3 -m pytest tests/test_macro_workspace_build.py -x -q
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.market_os.macro_workspaces import build, contract  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"


def _base_regime() -> dict:
    return {
        "asof": "2026-09-03", "date": "2026-09-03",
        "liquidity_overlay": "contracting",
        "liquidity_quality": {
            "asof": "2026-09-03", "label": "contracting", "quantity_roc_bn": -165.3,
            "rrp_buffer_bn": 6.7, "rrp_exhausted": True,
            "composition": {"mechanical": True},
            "stress_overlay": {"confirming_stress": False, "hy_oas_z": -0.2, "hy_oas_pct": 2.66},
            "walcl_stale_days": 1, "degraded": False,
        },
        "conditions": {
            "stale_inputs": [],
            "vintages": {
                "nfci": {"asof": "2026-08-28", "stale": False},
                "ofr_fsi": {"asof": "2026-08-30", "stale": False},
                "hy_oas": {"asof": "2026-09-02", "stale": False},
            },
            "financial_conditions": {"nfci": -0.558, "nfci_pctile": 0.046},
            "systemic_stress": {"ofr_fsi": -2.749, "ofr_fsi_pctile": 0.0278},
        },
        "regime_vector": {"rate_pressure_rates_scare_score": 43.2,
                          "rate_pressure_real10y_chg63_bp": 24.0},
    }


def _write_regime(tmp_path: Path) -> Path:
    p = tmp_path / "regime_latest.json"
    p.write_text(json.dumps(_base_regime()), encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# F5(a): atomic publish leaves exactly the two files, valid, hash-matched
# --------------------------------------------------------------------------- #
def test_atomic_publish_leaves_exactly_two_valid_hash_matched_files(tmp_path) -> None:
    regime_path = _write_regime(tmp_path)
    out_root = tmp_path / "out"
    receipt = build.build_liquidity_regime(
        regime_latest_path=regime_path, out_root=out_root, built_at=BUILT_AT, write=True,
    )
    files = sorted(p.relative_to(out_root).as_posix() for p in out_root.rglob("*") if p.is_file())
    assert files == ["workspaces/liquidity_regime/US/latest.json", "workspaces/manifest.json"]

    body = json.loads((out_root / "workspaces" / "liquidity_regime" / "US" / "latest.json")
                       .read_text(encoding="utf-8"))
    contract.validate(body)  # must not raise: real schema + hash validity
    assert body["generation"]["content_sha256"] == receipt["digest"]

    manifest = json.loads((out_root / "workspaces" / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["workspaces"]["liquidity_regime/US"]
    assert entry["content_sha256"] == receipt["digest"]
    assert entry["generation_id"] == body["generation"]["generation_id"]


# --------------------------------------------------------------------------- #
# F5(b): body written before manifest
# --------------------------------------------------------------------------- #
def test_body_written_before_manifest(tmp_path, monkeypatch) -> None:
    regime_path = _write_regime(tmp_path)
    out_root = tmp_path / "out"
    calls: list[str] = []
    original = build._atomic_write_bytes

    def _spy(path, data):
        calls.append(str(path))
        return original(path, data)

    monkeypatch.setattr(build, "_atomic_write_bytes", _spy)
    build.build_liquidity_regime(
        regime_latest_path=regime_path, out_root=out_root, built_at=BUILT_AT, write=True,
    )
    assert len(calls) == 2
    assert calls[0].endswith(str(Path("workspaces") / "liquidity_regime" / "US" / "latest.json"))
    assert calls[1].endswith(str(Path("workspaces") / "manifest.json"))


# --------------------------------------------------------------------------- #
# F5(c): manifest per-workspace hash equals the recomputed body digest
# --------------------------------------------------------------------------- #
def test_manifest_hash_matches_recomputed_body_digest(tmp_path) -> None:
    regime_path = _write_regime(tmp_path)
    out_root = tmp_path / "out"
    receipt = build.build_liquidity_regime(
        regime_latest_path=regime_path, out_root=out_root, built_at=BUILT_AT, write=True,
    )
    body = json.loads(Path(receipt["paths"]["workspace"]).read_text(encoding="utf-8"))
    manifest = json.loads(Path(receipt["paths"]["manifest"]).read_text(encoding="utf-8"))
    recomputed = contract.content_digest(body)
    assert body["generation"]["content_sha256"] == recomputed
    assert manifest["workspaces"]["liquidity_regime/US"]["content_sha256"] == recomputed


# --------------------------------------------------------------------------- #
# F5(d) / F2: identical owner input + built_at, different code_version ->
# identical digest and generation_id (code_version stays published as
# provenance, it is simply excluded from the hash).
# --------------------------------------------------------------------------- #
def test_code_version_does_not_affect_digest_or_generation_id(tmp_path) -> None:
    regime_path = _write_regime(tmp_path)
    receipt_a = build.build_liquidity_regime(
        regime_latest_path=regime_path, out_root=tmp_path / "out_a",
        built_at=BUILT_AT, code_version="commit-aaaaaaa", write=True,
    )
    receipt_b = build.build_liquidity_regime(
        regime_latest_path=regime_path, out_root=tmp_path / "out_b",
        built_at=BUILT_AT, code_version="commit-bbbbbbb", write=True,
    )
    assert receipt_a["digest"] == receipt_b["digest"]
    assert (receipt_a["snapshot"]["generation"]["generation_id"]
            == receipt_b["snapshot"]["generation"]["generation_id"])
    # code_version itself still differs in the published body (kept as provenance)
    assert receipt_a["snapshot"]["generation"]["code_version"] == "commit-aaaaaaa"
    assert receipt_b["snapshot"]["generation"]["code_version"] == "commit-bbbbbbb"


# --------------------------------------------------------------------------- #
# F4: CLI exit-code contract
# --------------------------------------------------------------------------- #
_CLI_PATH = ROOT / "scripts" / "build_macro_workspaces.py"
_CLI_SPEC = importlib.util.spec_from_file_location("build_macro_workspaces_cli", _CLI_PATH)
cli = importlib.util.module_from_spec(_CLI_SPEC)
_CLI_SPEC.loader.exec_module(cli)  # type: ignore[union-attr]


def _fake_receipt(availability_state: str) -> dict:
    snap = {
        "generation": {"generation_id": "liquidity_regime-US-deadbeefdeadbeef",
                        "code_version": "deadbeef"},
        "headline": {
            "state_id": "C",
            "state_label": {"en": "Easy funding / Weak support"},
            "quadrant": {"x": 10.0, "y": 20.0},
            "one_month_vector": {"dx": None, "dy": None, "status": "ABSENT", "null_reason": "WARMUP"},
        },
        "availability": {"state": availability_state, "contradiction": {"present": False}},
    }
    return {"snapshot": snap, "digest": "a" * 64, "bytes": 123, "manifest": {},
            "paths": {"workspace": None, "manifest": None}}


def test_cli_main_returns_0_when_current(monkeypatch) -> None:
    monkeypatch.setattr(cli._build, "build_liquidity_regime", lambda **kw: _fake_receipt("CURRENT"))
    assert cli.main(["--no-write"]) == 0


def test_cli_main_returns_0_when_late_within_tolerance(monkeypatch) -> None:
    monkeypatch.setattr(cli._build, "build_liquidity_regime",
                        lambda **kw: _fake_receipt("LATE_WITHIN_TOLERANCE"))
    assert cli.main(["--no-write"]) == 0


def test_cli_main_returns_2_when_typed_degraded(monkeypatch) -> None:
    monkeypatch.setattr(cli._build, "build_liquidity_regime",
                        lambda **kw: _fake_receipt("STALE_SOURCE"))
    assert cli.main(["--no-write"]) == 2


def test_cli_main_returns_1_on_hard_failure(monkeypatch, capsys) -> None:
    def _boom(**kw):
        raise RuntimeError("owner artifact missing")

    monkeypatch.setattr(cli._build, "build_liquidity_regime", _boom)
    rc = cli.main(["--no-write"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "RuntimeError" in err
    assert "owner artifact missing" in err


def test_cli_help_documents_exit_codes(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "Exit codes" in out
    assert "typed-degraded" in out
