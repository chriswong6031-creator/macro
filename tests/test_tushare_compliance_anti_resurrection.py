"""CI binding for the TuShare compliance anti-resurrection guard.

`DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE` settled TuShare
licensing privately.  `tests/test_china_tushare_spine.py` holds the RUNTIME out;
this file holds the PROSE out — the active authority surfaces (contract, R6
freeze/registry/command packet, workstreams, rights matrix, China Alpha rights
records) may describe the removed license-document gate only as history, never
as a live requirement.

Two things are asserted, because registering a guard is not the same as proving
it works: the repository is clean today, AND the guard still fails on a planted
violation.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / "scripts" / "check_tushare_compliance_resurrection.py"

sys.path.insert(0, str(REPO / "scripts"))
import check_tushare_compliance_resurrection as guard  # noqa: E402


def test_guard_script_exists_and_binds_the_named_authority_surfaces():
    """Sol's minimum set must be bound, not a convenient subset."""
    assert GUARD.is_file()
    required = {
        "research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md",
        "agentos/workstreams/WS-CN-LIMIT-ALPHA.md",
        "research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md",
        "research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_REGISTRY_V1_2026-08-19.json",
        "research/cn_limit/CN_LIMIT_R6_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md",
        "research/TUSHARE_P0_ENTITLEMENT_RIGHTS_MATRIX_2026-08-19.md",
        "research/china_alpha_intelligence/RIGHTS_REGISTRY.md",
        "research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md",
        "research/china_alpha_intelligence/commissions/RIGHTS-0_source_entitlement_audit.md",
    }
    missing = sorted(required - set(guard.GUARDED_PATHS))
    assert missing == [], f"guard does not bind required authority surfaces: {missing}"
    absent = [rel for rel in guard.GUARDED_PATHS if not (REPO / rel).is_file()]
    assert absent == [], f"guarded paths do not exist: {absent}"


def test_repository_carries_no_active_tushare_license_requirement():
    result = subprocess.run(
        [sys.executable, str(GUARD)], capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "clean" in result.stdout


@pytest.mark.parametrize(
    "line",
    [
        "| Derived model/display | UNKNOWN. Confirm with vendor before any commercial dashboard. |",
        "A commercial named-actor chip needs an explicit vendor yes.",
        "DEP-EXACT is pending one operator-owned vendor letter.",
        "Collection requires a written commercial grant before the first request.",
        "The collector requires an authorization receipt and a trust allowlist.",
    ],
)
def test_guard_rejects_a_planted_active_requirement(line):
    """A guard that cannot fail is decoration."""
    reason = guard.scan_line(
        "research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md", line, line,
    )
    assert reason is not None, f"guard failed to reject: {line}"


@pytest.mark.parametrize(
    "line",
    [
        "[NULL / SUPERSEDED 2026-08-21] the former vendor letter precondition no longer applies.",
        "- no reintroduced authorization-receipt/trust-allowlist/license-document gate",
        "no vendor letter is required or may be requested",
        "The former `--authorization-receipt` flag was removed from the runtime.",
    ],
)
def test_guard_allows_explicit_historical_tombstones(line):
    reason = guard.scan_line(
        "research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md", line, line,
    )
    assert reason is None, f"guard wrongly rejected a tombstone: {line} -> {reason}"


def test_a_negation_in_a_later_cell_cannot_excuse_an_earlier_requirement():
    """Sol's cited row: a live verdict cell followed by unrelated prose.

    The row's third cell says the native collector "structurally cannot answer"
    — judging the whole line would let that `cannot` excuse the requirement two
    cells earlier, which is exactly how this row survived the first sweep.
    """
    row = (
        "| Derived-use / display rights | UNKNOWN. A commercial named-actor chip needs an "
        "explicit vendor yes (CN-A section 2.6b). | **N/A for named actors** -- the native "
        "collector structurally cannot answer the named-actor question. |"
    )
    reason = guard.scan_line(
        "research/china_alpha_intelligence/RIGHTS_REGISTRY.md", row, row,
    )
    assert reason is not None and "explicit vendor yes" in reason


def test_guard_leaves_other_vendors_alone():
    """The override is TuShare-specific; UNKNOWN_RIGHTS stays legal elsewhere."""
    sina = (
        "| Sina holder tables (via akshare) | ... | **UNKNOWN_RIGHTS at the margin** "
        "-- no Sina-specific ToS statement was found. |"
    )
    assert guard.scan_line(
        "research/china_alpha_intelligence/RIGHTS_REGISTRY.md", sina, sina,
    ) is None


def test_guard_reports_a_missing_guarded_surface(monkeypatch, capsys):
    """A vanished input must fail loudly, never pass silently."""
    monkeypatch.setattr(
        guard, "GUARDED_PATHS", ("research/DOES_NOT_EXIST_ANYWHERE.md",),
    )
    assert guard.main() == 1
    captured = capsys.readouterr().out
    assert captured.startswith("::error") or "::error" in captured
    assert "guarded path is missing" in captured
