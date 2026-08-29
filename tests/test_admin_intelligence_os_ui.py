"""Executable client contract for the Eval OS A1 evidence view.

The page is vanilla JavaScript.  These tests execute the exact pure rendering block from
``admin/static/app.js`` under Node rather than grepping for labels: the assertions cover
the HTML an authenticated operator actually receives from the view helpers.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
APP = REPO / "admin" / "static" / "app.js"
START = "/* IOS_EVIDENCE_CONTRACT_START */"
END = "/* IOS_EVIDENCE_CONTRACT_END */"


def _contract() -> str:
    source = APP.read_text(encoding="utf-8")
    assert START in source and END in source, (
        "the existing Intelligence OS page must expose its pure evidence rendering "
        "contract for executable client tests"
    )
    return source.split(START, 1)[1].split(END, 1)[0]


def _run(cases: list[dict]) -> list[dict]:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError("Node is required for the Intelligence OS client contract")
        pytest.skip("node not available to execute the client contract")
    harness = f"""
const esc = (s) => String(s == null ? "" : s).replace(/[&<>\"']/g, c => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '\"': "&quot;", "'": "&#39;" }}[c]));
const fmtNum = (n) => n == null ? "—" : Number(n).toLocaleString("en-US");
{_contract()}
const cases = JSON.parse(process.argv[2]);
const out = cases.map(c => ({{
  classes: c.statuses.map(iosEvidenceStatusCls),
  bands: iosNormalizeCeoBands(c.bands),
  cell: iosEvidenceCell(c.engine),
  detail: iosEvidenceDetailCard(c.engine),
}}));
console.log(JSON.stringify(out));
"""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "intelligence_os_contract.mjs"
        path.write_text(harness, encoding="utf-8")
        run = subprocess.run(
            [node, str(path), json.dumps(cases)],
            capture_output=True,
            text=True,
            check=False,
        )
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(run.stdout)


def test_evidence_bands_are_complete_ordered_and_visually_distinct():
    result = _run(
        [
            {
                "statuses": [
                    "Validated",
                    "Accruing",
                    "Ungraded by design",
                    "Degraded",
                    "Disproven",
                ],
                # Deliberately omit the empty Validated band. The client must still
                # render it: zero is evidence here, not an absent answer.
                "bands": [
                    {"evidence_status": "Disproven", "n_engines": 1},
                    {"evidence_status": "Accruing", "n_engines": 7},
                ],
                "engine": {},
            }
        ]
    )[0]

    assert result["classes"] == ["s-ok", "s-warn", "s-mut", "s-bad", "s-bad"]
    assert [row["evidence_status"] for row in result["bands"]] == [
        "Validated",
        "Accruing",
        "Ungraded by design",
        "Degraded",
        "Disproven",
    ]
    assert result["bands"][0]["n_engines"] == 0
    assert result["bands"][1]["n_engines"] == 7


def test_detail_card_renders_lawful_evidence_without_a_score():
    engine = {
        "evidence_status": "Accruing",
        "evidence_reason_codes": ["immature_evidence", "mixed_explicit_bases"],
        "evidence_refs": ["qledger:stock_desk:horizon:21"],
        "evidence_provider": {
            "kind": "qledger",
            "binding": "adapter:stock_desk",
            "family": "stock_desk",
            "read_status": "ok",
        },
        "evidence_ruler": {
            "declared_horizon": {"horizon_d": [21], "horizon_unit": "trading_days"},
            "selected_qledger_rung": "21",
            "qledger_clock": {"git_sha": "abc123"},
        },
        "evidence_basis": {
            "clock_basis_by_horizon": {"21": "explicit"},
            "evidence_basis_by_horizon": {"21": "forward_return"},
            "pooling_refused": True,
        },
        "evidence_maturity": {
            "validation_state": "phase0",
            "rungs": {"21": {"n_dates": 7, "needed": 25}},
        },
        "validation_state": "phase0",
        "validation_state_evidence": {"reason": "no_species_bound"},
        "output_class": None,
        "graded_by_design": "yes",
        "graded_by_design_source": "derived: owner ledger",
    }
    html = _run([{"statuses": [], "bands": [], "engine": engine}])[0]["detail"]

    for visible in (
        "Accruing",
        "adapter:stock_desk",
        "trading_days",
        "pooling_refused",
        "immature_evidence",
        "mixed_explicit_bases",
        "qledger:stock_desk:horizon:21",
        "phase0",
        "output class",
        "null",
    ):
        assert visible in html
    assert "evidence_score" not in html
    assert "Evidence score" not in html


def test_noncanonical_detail_renders_registry_gap_not_an_evidence_disposition():
    rendered = _run(
        [
            {
                "statuses": [],
                "bands": [],
                "engine": {
                    "canonical_t1": False,
                    "evidence_status": None,
                    "evidence_reason_codes": ["not_canonical_t1"],
                },
            }
        ]
    )[0]
    html = rendered["detail"]

    assert "Registry gap" in html
    assert "No T1 evidence disposition" in html
    assert "Accruing" not in html
    assert "Registry gap" in rendered["cell"]
    assert "Accruing" not in rendered["cell"]
