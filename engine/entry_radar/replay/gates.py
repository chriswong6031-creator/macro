"""§14 mechanical enforcement — the prereg gates the replay runner MUST pass.

Pure logic: every environmental fact (file bytes, git ancestry answers, ledger
rows, registry hashes) is INJECTED so tests can prove each gate refuses on a
mutated input (battery C).  The runner (`scripts/entry_radar_replay.py`) supplies
real inputs; nothing here touches the network, git, or the filesystem beyond the
paths it is handed.

Refusal is an exception, never a return code — mirroring
``engine.rule_experiments.verify_spec_hashes``'s GovernorRefusal discipline.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, Mapping

from engine.entry_radar.replay import prereg


class PreregGateRefusal(RuntimeError):
    """A §14 gate failed.  The message names the gate and the mismatch."""


@dataclass(frozen=True)
class GateReceipt:
    """What each passed gate verified — recorded into the results package."""

    gate: str
    detail: str


def _refuse(gate: str, msg: str) -> None:
    raise PreregGateRefusal(f"{gate}: {msg}")


# --------------------------------------------------------------------------- #
# G-1 — prereg frozen-prefix hash (B4: amendments append AFTER the marker and
# never change this hash; any edit to the frozen body refuses)
# --------------------------------------------------------------------------- #
def frozen_prefix(doc_bytes: bytes) -> bytes:
    """The bytes G-1 hashes: everything up to and INCLUDING the §16 marker line.

    Refuses (fail-closed) when the marker is absent — a prereg without its
    amendment fence is not the frozen document.
    """
    marker = prereg.PREREG_FROZEN_MARKER.encode("utf-8")
    idx = doc_bytes.find(marker)
    if idx < 0:
        _refuse("G-1", f"frozen marker {prereg.PREREG_FROZEN_MARKER!r} absent "
                       "from the prereg document")
    end = doc_bytes.find(b"\n", idx)
    if end < 0:
        end = len(doc_bytes)
    return doc_bytes[: end + 1]


def check_doc_hash(doc_bytes: bytes) -> GateReceipt:
    """G-1: sha256 of the prereg's FROZEN PREFIX equals the PR-5b constant."""
    if prereg.PREREG_DOC_SHA256 == "UNSET":
        _refuse("G-1", "PREREG_DOC_SHA256 is UNSET — the prereg has not been "
                       "stamped into the runner (PR-5a unmerged or PR-5b unstamped)")
    got = hashlib.sha256(frozen_prefix(doc_bytes)).hexdigest()
    if got != prereg.PREREG_DOC_SHA256:
        _refuse("G-1", f"prereg frozen-prefix sha256 {got} != frozen "
                       f"{prereg.PREREG_DOC_SHA256}")
    return GateReceipt("G-1", f"frozen-prefix sha256 {got}")


# --------------------------------------------------------------------------- #
# G-2 — merged ancestry
# --------------------------------------------------------------------------- #
def check_merged_ancestry(is_ancestor_of_head: Callable[[str], bool]) -> GateReceipt:
    """G-2: the recorded prereg commit is an ancestor of the runner's HEAD.

    ``is_ancestor_of_head`` is injected (the runner passes a closure over
    ``git merge-base --is-ancestor``); a False answer or a raised error refuses.
    """
    if prereg.PREREG_COMMIT == "UNSET":
        _refuse("G-2", "PREREG_COMMIT is UNSET — no merged prereg commit recorded")
    if not re.fullmatch(r"[0-9a-f]{40}", prereg.PREREG_COMMIT):
        _refuse("G-2", f"PREREG_COMMIT {prereg.PREREG_COMMIT!r} is not a 40-hex sha")
    try:
        ok = bool(is_ancestor_of_head(prereg.PREREG_COMMIT))
    except Exception as exc:  # noqa: BLE001 — fail closed, name the failure
        _refuse("G-2", f"ancestry probe raised {exc!r} (fail-closed)")
    if not ok:
        _refuse("G-2", f"prereg commit {prereg.PREREG_COMMIT} is not an ancestor of HEAD")
    return GateReceipt("G-2", f"prereg commit {prereg.PREREG_COMMIT} is merged history")


# --------------------------------------------------------------------------- #
# G-3 — TrialLedger declared-budget admission
# --------------------------------------------------------------------------- #
def check_budget_row(ledger_lines: Iterable[str]) -> GateReceipt:
    """G-3: data/trial_ledger.jsonl holds the §13 declared_budget row whose
    reason carries exactly the G-1/G-2 identifiers and the declared 253 —
    AND the ledger already carries pre-existing unrelated families (the §13
    anti-truncation assertion: a sparse-tree write would have replaced the
    fleet ledger with a one-family file; that state refuses)."""
    want_reason_bits = (
        f"w5_prereg={prereg.PREREG_COMMIT}",
        f"doc_sha256={prereg.PREREG_DOC_SHA256}",
    )
    found = False
    other_families: set[str] = set()
    for line in ledger_lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001 — torn line tolerated, never counted
            continue
        fam = row.get("family")
        if fam and fam != prereg.TRIAL_FAMILY:
            other_families.add(str(fam))
        if (row.get("kind") == "declared_budget"
                and fam == prereg.TRIAL_FAMILY
                and int(row.get("n", -1)) == prereg.DECLARED_BUDGET):
            reason = str(row.get("reason") or "")
            if all(bit in reason for bit in want_reason_bits):
                found = True
    if not found:
        _refuse("G-3", "no declared_budget row for family "
                       f"{prereg.TRIAL_FAMILY!r} with n={prereg.DECLARED_BUDGET} "
                       "carrying the frozen prereg identifiers")
    if not other_families:
        _refuse("G-3", "trial ledger carries no pre-existing families — this is "
                       "the sparse-tree truncation signature; refuse rather than "
                       "bless a corrupt store")
    return GateReceipt(
        "G-3", f"budget row n={prereg.DECLARED_BUDGET} admitted beside "
               f"{len(other_families)} pre-existing families")


def check_look_cell(cell: str) -> None:
    """§13/M10: the look-logger refuses any cell name outside LOOK_CELLS."""
    if cell not in prereg.LOOK_CELLS:
        _refuse("G-3", f"look cell {cell!r} is not one of the {prereg.DECLARED_BUDGET} "
                       "declared cells — an undeclared look requires a §16 amendment "
                       "and a LOOK_CELLS addition first")


# --------------------------------------------------------------------------- #
# G-4 — detector spec hashes
# --------------------------------------------------------------------------- #
def check_spec_hashes(live_hashes: Mapping[str, str],
                      f1_refuses: Callable[[], bool]) -> GateReceipt:
    """G-4: every §1 hash matches the live DETECTORS registry; F1 still refuses.

    ``live_hashes`` maps detector_id -> recomputed spec hash (the runner builds
    it from ``engine.entry_radar.detectors``); ``f1_refuses`` returns True iff
    ``get_spec("F1_FUSION")`` raises NotYetSpecified.
    """
    for det, want in prereg.EXPECTED_SPEC_HASHES.items():
        got = live_hashes.get(det)
        if got != want:
            _refuse("G-4", f"{det}: live spec hash {got!r} != frozen {want!r} "
                           "(a firing-relevant change requires a NEW detector "
                           "version and a fresh registration)")
    extra = set(live_hashes) - set(prereg.EXPECTED_SPEC_HASHES)
    if extra:
        _refuse("G-4", f"unregistered detectors present: {sorted(extra)}")
    try:
        if not f1_refuses():
            _refuse("G-4", "F1_FUSION no longer refuses (NotYetSpecified expected)")
    except PreregGateRefusal:
        raise
    except Exception as exc:  # noqa: BLE001
        _refuse("G-4", f"F1 refusal probe raised {exc!r} (fail-closed)")
    return GateReceipt("G-4", "6 spec hashes match; F1 refuses")


# --------------------------------------------------------------------------- #
# G-5 — staged-Terminal fidelity (evidence injected by the staging script)
# --------------------------------------------------------------------------- #
def check_staging_fidelity(report: Mapping[str, object]) -> GateReceipt:
    """G-5: the staged emitter reproduced the W2 fixture dots + known_ts exactly.

    ``report`` is produced by ``scripts/entry_radar_stage_terminal.py`` and must
    carry: ``terminal_pin`` (the git sha staged), and per fixture name a
    ``match`` bool with counts.  Any mismatch, absent name, or wrong pin refuses.
    """
    if str(report.get("terminal_pin")) != prereg.TERMINAL_PIN:
        _refuse("G-5", f"staged pin {report.get('terminal_pin')!r} != "
                       f"frozen {prereg.TERMINAL_PIN}")
    names = report.get("fixtures")
    if not isinstance(names, Mapping) or not names:
        _refuse("G-5", "staging report carries no fixture comparisons")
    bad = [n for n, r in names.items()
           if not (isinstance(r, Mapping) and r.get("match") is True)]
    if bad:
        _refuse("G-5", f"fixture mismatch on {sorted(bad)}")
    return GateReceipt("G-5", f"fixture parity on {sorted(names)}")


# --------------------------------------------------------------------------- #
# G-6 — holdout fence
# --------------------------------------------------------------------------- #
def check_decision_in_era(decision_session: date) -> None:
    """G-6 (per-episode): refuse any decision session inside the holdout.

    Called on EVERY episode before outcomes attach; also the era filter's own
    unit test target (battery D).
    """
    if decision_session > prereg.HOLDOUT_BOUNDARY:
        _refuse("G-6", f"decision session {decision_session.isoformat()} is in the "
                       f"holdout (> {prereg.HOLDOUT_BOUNDARY.isoformat()}); W5 may "
                       "not read it")
    if decision_session < prereg.REPLAY_ERA_START:
        _refuse("G-6", f"decision session {decision_session.isoformat()} predates "
                       f"the replay era start {prereg.REPLAY_ERA_START.isoformat()}")


def run_all(*, doc_bytes: bytes,
            is_ancestor_of_head: Callable[[str], bool],
            ledger_lines: Iterable[str],
            live_hashes: Mapping[str, str],
            f1_refuses: Callable[[], bool],
            staging_report: Mapping[str, object]) -> list[GateReceipt]:
    """Run G-1..G-5 in order (G-6 is per-episode).  Returns receipts or raises."""
    return [
        check_doc_hash(doc_bytes),
        check_merged_ancestry(is_ancestor_of_head),
        check_budget_row(ledger_lines),
        check_spec_hashes(live_hashes, f1_refuses),
        check_staging_fidelity(staging_report),
    ]


__all__ = [
    "PreregGateRefusal", "GateReceipt", "frozen_prefix", "check_doc_hash",
    "check_merged_ancestry", "check_budget_row", "check_look_cell",
    "check_spec_hashes", "check_staging_fidelity", "check_decision_in_era",
    "run_all",
]
