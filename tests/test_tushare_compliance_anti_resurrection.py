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


# --- vendor-approval INSTRUCTIONS (Sol re-review 2026-08-22) ------------------
#
# The mechanism nouns were bound from the start; the DIRECTIVES were not.  Four
# live clauses sat inside guarded files and the guard was green:
#   matrix 2.1  "Ask vendor in writing: (1) may we retain stk_surv locally ..."
#   matrix 2.4  "... and the vendor confirms commercial derived use of Q&A text"
#   matrix 2.6  "... still do not buy until the vendor confirms named-actor ..."
#   matrix 3    summary column heading "Vendor must confirm before product use"
# plus a fifth this sweep found on its own: WS-TUSHARE-ENTITLEMENT's next_action
# read "asks Tushare in writing the five commercial questions".

MATRIX = "research/TUSHARE_P0_ENTITLEMENT_RIGHTS_MATRIX_2026-08-19.md"
WS_ENTITLEMENT = "agentos/workstreams/WS-TUSHARE-ENTITLEMENT.md"
CONTRACT = "research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md"


@pytest.mark.parametrize(
    "rel,line",
    [
        # The four Sol named, verbatim as they stood before this amendment.
        (MATRIX,
         "| **Recommended action** | **Do not buy.** Confirm on the privilege page "
         "that 5000. Ask vendor in writing: (1) may we retain `stk_surv` locally, "
         "(2) may a commercial product display *derived* visit intensity. |"),
        (MATRIX,
         "| **Recommended action** | **Do not buy.** Revisit only if a backfill is "
         "chartered **and** the vendor confirms commercial derived use of Q&A text. |"),
        (MATRIX,
         "| Personal / institutional price | No extra SKU if 10000 unlocks `hm_detail`. "
         "That is a **MISSING** convert -- still do not buy until the vendor confirms "
         "named-actor commercial use. |"),
        (MATRIX,
         "| P0 family | Status | Buy? | Personal | Inst. | "
         "Vendor must confirm before product use |"),
        # The fifth, found by this sweep: the addressee is named, not called "vendor".
        (WS_ENTITLEMENT,
         "  SKU list, then asks Tushare in writing the five commercial questions in"),
        # Equivalent shapes a future session might reach for.
        (CONTRACT, "Ask the vendor in writing whether commercial derived display is permitted."),
        (CONTRACT, "This stays blocked until Tushare confirms institutional commercial use."),
        (CONTRACT, "Vendor must confirm before any product use of derived signals."),
        (CONTRACT, "Obtain vendor sign-off before the first paid request."),
        (CONTRACT, "Raise with the vendor whether bulk local retention is in scope."),
        (CONTRACT, "Send a written enquiry to the vendor covering retention and display."),
    ],
)
def test_guard_rejects_an_active_vendor_approval_instruction(rel, line):
    assert guard.scan_line(rel, line, line) is not None, f"guard failed to reject: {line}"


def test_an_unrelated_negation_cannot_excuse_a_vendor_instruction():
    """The 2.6 shape: the negation governs *buy*, not the vendor step.

    `do not` used to sit in the general NEGATION list, so any clause containing
    it was excused wholesale -- which is how "still do not buy until the vendor
    confirms named-actor commercial use" passed.  A bare `do not` now counts only
    when it directly governs the instruction.
    """
    line = ("| Personal / institutional price | still do not buy until the vendor "
            "confirms named-actor commercial use. |")
    reason = guard.scan_line(MATRIX, line, line)
    assert reason is not None and "vendor-approval instruction" in reason


@pytest.mark.parametrize(
    "line",
    [
        "No coding session may ask the vendor anything; compliance is settled privately.",
        "The house never asks the vendor to re-verify a settled private agreement.",
        "This lane must not confirm with the vendor before a request.",
        '[NULL per DEC:...] the former "vendor must confirm" column is SUPERSEDED.',
        "[NULL per section 0.0: the former vendor-confirmation precondition no longer applies.]",
    ],
)
def test_guard_allows_a_prohibition_or_tombstone_that_governs_the_instruction(line):
    assert guard.scan_line(CONTRACT, line, line) is None, f"wrongly rejected: {line}"


def test_a_tombstone_in_a_neighbouring_table_cell_cannot_excuse_a_live_cell():
    """Same failure family as the negation hole, one level up.

    Tombstone markers used to count from a +/-2 line window even for table rows,
    so a `NULL / SUPERSEDED` in a different cell -- or a different ROW -- excused
    a live verdict.  Markdown prose wraps and still gets the window; a table row
    does not, so its scope is the cell.
    """
    row = ("| Derived-use rights | UNKNOWN. A commercial chip needs a vendor letter "
           "first. | NULL / SUPERSEDED 2026-08-21, unrelated cell. |")
    assert guard.scan_line(MATRIX, row, row) is not None
    prose = ("a commercial chip needs a vendor letter first\n"
             "[NULL / SUPERSEDED 2026-08-21 -- this precondition was removed]")
    assert guard.scan_line(
        CONTRACT, "a commercial chip needs a vendor letter first", prose,
    ) is None


@pytest.mark.parametrize(
    "label",
    [
        "Raw redistribution", "Product-display rights", "Persistence rights",
        "Persistence / derived-use rights", "Persistence / derived-use / display",
        "Derived model/display", "Derived-use rights", "Derived-use / display rights",
    ],
)
def test_every_rights_row_label_spelling_is_bound(label):
    """A guard narrower than the threat is the same defect as no guard.

    The first label list carried four of the eight spellings actually in use, so
    three `Persistence rights | UNKNOWN` rows in RIGHTS_REGISTRY stayed invisible.
    """
    row = f"| {label} | UNKNOWN (CN-A). | native route keeps its own verdict. |"
    assert guard.scan_line(
        "research/china_alpha_intelligence/RIGHTS_REGISTRY.md", row, row,
    ) is not None, f"unbound rights label: {label}"


def test_the_four_named_phrasings_are_gone_from_the_rights_matrix():
    """Sol's acceptance condition, asserted against the file itself."""
    text = (REPO / MATRIX).read_text(encoding="utf-8")
    for phrase in (
        "Ask vendor in writing",
        "the vendor confirms commercial derived use",
        "do not buy until the vendor confirms",
        "Vendor must confirm before product use |",
    ):
        assert phrase not in text, f"active phrasing survives in the matrix: {phrase}"


def test_surviving_vendor_wording_in_guarded_files_is_tombstoned():
    """Anything left standing must be inside an explicit NULL/SUPERSEDED clause."""
    live = []
    for rel in guard.GUARDED_PATHS:
        path = REPO / rel
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            hit = guard._first_match(guard.FORBIDDEN_INSTRUCTION, line)
            if hit is None:
                continue
            clause = guard._enclosing_clause(line, hit.start())
            if not guard._hits(guard.STRONG_TOMBSTONE, clause):
                live.append(f"{rel}:{index + 1}: {line.strip()[:120]}")
    assert live == [], "un-tombstoned vendor-approval wording: " + "; ".join(live)


def test_the_full_a_contract_has_no_licensing_gap_heading():
    """There is no active licensing gap, so the heading may not claim one."""
    text = (REPO / CONTRACT).read_text(encoding="utf-8")
    assert "## Remaining technical/data gaps" in text
    assert "Remaining licensing/data gaps" not in text


def test_the_live_workstreams_current_handoff_is_guarded():
    """Handoffs are history -- except the CURRENT one, which is also instruction.

    AgentOS treats a workstream's latest handoff `do_not_redo` / `next_actions`
    as binding on the next session. WS:TUSHARE-ENTITLEMENT's still said "send
    Tushare the five questions" and "rights questions go to a vendor letter",
    and it was outside the guard because handoffs are not guarded as a class.
    """
    assert "agentos/handoffs/TUSHARE-ENTITLEMENT-2026-08-19.md" in guard.GUARDED_PATHS
    text = (REPO / "agentos/handoffs/TUSHARE-ENTITLEMENT-2026-08-19.md").read_text(
        encoding="utf-8"
    )
    assert "send Tushare the five questions" not in text
    assert "Rights questions go to a vendor letter" not in text


@pytest.mark.parametrize(
    "line",
    [
        # "until the TuShare <thing> exists" is a BUILD precondition, not a
        # compliance one -- the approval verb is what makes it the latter.
        "Until the TuShare daily + stk_limit spine exists and passes section 1, hold.",
        "Nothing ships until Tushare coverage is proven for the 2016+ window.",
        "Trade dates worth asking the vendor for, newest first.",
    ],
)
def test_guard_does_not_flag_build_preconditions_that_merely_name_the_vendor(line):
    assert guard.scan_line(CONTRACT, line, line) is None, f"false positive: {line}"
