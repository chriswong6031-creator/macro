#!/usr/bin/env python3
"""Fail-closed verification for the research-only GD-1C artifact set."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
FREEZE = "fce7bfeb8c925748ed92b54a7b19901c3a9f35c1"
FREEZE_CONTENT_SHA256 = "d197cfaab658924124c117246227dd17aae334938e0b3ba55fff3ddc264e3aed"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    freeze_paths = git("diff-tree", "--no-commit-id", "--name-only", "-r", FREEZE).splitlines()
    assert freeze_paths == ["research/grey_deer/gd1c/GD1C_PREREG_2026-08-19.md"]
    freeze_content = subprocess.check_output(
        ["git", "show", f"{FREEZE}:research/grey_deer/gd1c/GD1C_PREREG_2026-08-19.md"],
        cwd=ROOT,
    )
    assert hashlib.sha256(freeze_content).hexdigest() == FREEZE_CONTENT_SHA256

    rows = pd.read_csv(HERE / "GD1C_RECONSTRUCTION_ROWS.csv", parse_dates=["observation_session"])
    episodes = pd.read_csv(HERE / "GD1C_EPISODE_LEDGER.csv", parse_dates=["episode_anchor"])
    gates = pd.read_csv(HERE / "GD1C_GATE_SCORECARD.csv")
    manifest = json.loads((HERE / "GD1C_RECONSTRUCTION_MANIFEST.json").read_text())
    receipt = json.loads((HERE / "GD1C_RUN_RECEIPT.json").read_text())

    assert len(rows) == 2672
    assert len(episodes) == 556
    assert len(gates) == 8
    assert set(rows["lane"]) == {"def_current_cf"}
    assert set(episodes["lane"]) == {"def_current_cf"}
    assert set(gates["primary_verdict"]) == {"BLOCKED"}
    assert not gates["all_secondary_numeric_gates"].any()
    assert manifest["primary_lane"]["verdict"] == "BLOCKED"
    assert manifest["primary_lane"]["evaluated_rows"] == 0
    assert manifest["secondary_lane"]["lane"] == "def_current_cf"
    assert receipt["primary_verdicts"] == {"GD-H1": "BLOCKED", "GD-H2": "BLOCKED"}

    required_gate_fields = {
        "effective_N", "raw_fire_N", "adverse_N", "era_N", "oos_average_precision",
        "ap_over_prevalence", "ap_ratio_lb90", "brier_skill_half_1",
        "brier_skill_half_2", "calibration_slope", "lead_median", "lead_p25",
        "false_episode_max_per_quarter", "required_source_coverage", "bh_q_value",
    }
    assert required_gate_fields <= set(gates.columns)
    assert episodes["episode_anchor"].max() <= pd.Timestamp("2026-07-31")
    assert not episodes.duplicated(["hypothesis", "endpoint", "episode_anchor"]).any()

    design_dates = rows.loc[
        (rows.observation_session >= pd.Timestamp("2016-01-04"))
        & (rows.observation_session <= pd.Timestamp("2026-07-31")),
        "observation_session",
    ].reset_index(drop=True)
    positions = {date: pos for pos, date in enumerate(design_dates)}
    for _, group in episodes.groupby(["hypothesis", "endpoint", "held_out_era"]):
        dates = group.episode_anchor.sort_values().tolist()
        assert all(positions[b] - positions[a] > 3 for a, b in zip(dates[:-1], dates[1:]))

    assert manifest["analysis_script_sha256"] == sha256(HERE / "GD1C_RECONSTRUCT_AND_TEST.py")
    for item in manifest["input_inventories"]:
        assert sha256(ROOT / item["path"]) == item["sha256"]
    for name, digest in receipt["artifact_sha256"].items():
        assert sha256(HERE / name) == digest

    assert git("status", "--porcelain", "--", "data", "site") == ""
    print(json.dumps({
        "status": "PASS",
        "freeze_sha": FREEZE,
        "reconstruction_rows": len(rows),
        "episode_endpoint_rows": len(episodes),
        "gate_rows": len(gates),
        "primary_verdicts": receipt["primary_verdicts"],
        "secondary_pass": bool(gates["all_secondary_numeric_gates"].any()),
        "data_site_dirty": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
