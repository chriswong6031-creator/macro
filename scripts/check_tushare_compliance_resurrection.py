#!/usr/bin/env python3
"""Fail if an ACTIVE authority surface re-requires TuShare licensing documents.

`DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE` (Chairman override,
2026-08-21) settled TuShare licensing/compliance privately and put the evidence
outside coding scope.  The runtime gate is already held out by unit tests, but
the durable risk is prose: a future session greps the repo, finds a row-level
verdict like "vendor letter before any commercial display" in a masterplan or a
rights matrix, and treats a closed question as open again.

This guard binds the ACTIVE authority surfaces listed in ``GUARDED_PATHS``.  A
forbidden phrase is allowed only inside an explicit historical tombstone; a
phrase that also carries requirement grammar ("requires", "pending", "before
any") needs the strong tombstone form (NULL / SUPERSEDED / CANCELLED /
HISTORICAL / FORMERLY / no longer / not required).

Scope is TuShare only.  Other vendors keep their own licensing controls, and
`UNKNOWN_RIGHTS` remains legal for them -- see the RIGHTS_REGISTRY carve-out.

Run:  python3 scripts/check_tushare_compliance_resurrection.py
Exit: 0 clean, 1 on any active resurrection.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Active authority surfaces.  A file listed here may DESCRIBE the removed gate
# only as history; it may never require it.
GUARDED_PATHS = (
    "collectors/china_tushare_spine.py",
    ".github/workflows/tushare-spine-backfill.yml",
    "contracts/cn_tushare_a_share_spine_manifest.v1.schema.json",
    "research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md",
    "research/CN_LIMIT_EXACT_PLANE_LEDGER_PREREG_REQUIREMENTS_2026-08-11.md",
    "research/TUSHARE_P0_ENTITLEMENT_RIGHTS_MATRIX_2026-08-19.md",
    "research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md",
    "research/china_alpha_intelligence/RIGHTS_REGISTRY.md",
    "research/china_alpha_intelligence/commissions/RIGHTS-0_source_entitlement_audit.md",
    "research/MASTERMIND_DATA_SOURCE_CATALOG.md",
    "research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md",
    "research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_REGISTRY_V1_2026-08-19.json",
    "research/cn_limit/CN_LIMIT_R6_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md",
    "agentos/workstreams/WS-CN-LIMIT-ALPHA.md",
    "agentos/workstreams/WS-TUSHARE-ENTITLEMENT.md",
)

# The license-document mechanism, in any spelling.
FORBIDDEN = (
    r"vendor[- ]letter",
    r"written (?:commercial|institutional|vendor)[- ]grant",
    r"authorization[- _]receipt",
    r"authorization[- _]trust[- _]allowlist",
    r"trust[- ]allowlist",
    r"grant[- _]document",
    r"entitlement[- _]chain",
    r"cn_tushare_written_authorization",
    r"CODE_REVIEWED_AUTHORIZATION",
    r"AuthorizationGrant",
    r"explicit vendor yes",
    r"license (?:upload|document)",
    # The resurrection does not need a license noun: a rights cell that tells a
    # future session to go ask the vendor reopens the closed question just as
    # effectively.
    r"confirm (?:with|from|via) (?:the )?vendor",
    r"vendor (?:confirmation|approval|sign-?off|yes)\b",
    r"rights[- ]unknown",
    # The bare verdict-cell shape Sol flagged: "| Derived model/display | UNKNOWN".
    r"\|\s*(?:Derived[ -](?:model/display|use rights)|Raw redistribution|"
    r"Product-display rights|Persistence / derived-use / display)\s*\|\s*UNKNOWN",
)

# The pre-override verdict tag.  Legal for other vendors, never for TuShare.
TAG_PATTERN = r"UNKNOWN_RIGHTS"
TAG_SCOPED_PATHS = frozenset({
    "research/TUSHARE_P0_ENTITLEMENT_RIGHTS_MATRIX_2026-08-19.md",
    "research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md",
    "research/china_alpha_intelligence/commissions/RIGHTS-0_source_entitlement_audit.md",
    "agentos/workstreams/WS-TUSHARE-ENTITLEMENT.md",
})
# RIGHTS_REGISTRY covers several vendors; the tag survives only where the line
# is explicitly about a non-TuShare source or is the tag definition itself.
MIXED_VENDOR_PATHS = frozenset({"research/china_alpha_intelligence/RIGHTS_REGISTRY.md"})
NON_TUSHARE_MARKERS = (r"sina", r"akshare", r"non-tushare")

# Wording that makes the phrase a prohibition or a dead historical artifact.
# Checked FIRST: "no vendor letter is required" contains requirement grammar but
# is the opposite of a requirement.
NEGATION = (
    r"\bno (?:vendor|written|authorization|reintroduced|license|such|longer)\b",
    r"\bnot required\b", r"\bnever\b", r"\bmust not\b", r"\bmay not\b",
    r"\bdo not\b", r"\bcannot\b", r"\bforbidden\b", r"\bprohibit", r"\brefus",
    r"\bremoved\b", r"\bnulls?\b", r"\bthe former\b", r"\brenamed\b",
    r"\bhistorical\b", r"\bsuperseded\b", r"\bcancelled\b", r"\bformerly\b",
)
# Sanctioned tombstone wording, strong enough to excuse requirement grammar.
STRONG_TOMBSTONE = (
    r"\bNULL\b", r"SUPERSEDED", r"CANCELLED", r"HISTORICAL", r"FORMERLY",
    r"no longer", r"not required", r"never required", r"pre-2026-08-21",
    r"\bthe former\b", r"\bnulls?\b", r"\brenamed\b",
)
WEAK_TOMBSTONE = STRONG_TOMBSTONE + NEGATION + (
    r"anti-resurrection", r"DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE",
    r"CHAIRMAN_VERIFIED_PRIVATE",
)
# Grammar that turns a mention into a live precondition.
REQUIREMENT = (
    r"requires?\b", r"required\b", r"pending\b", r"before any\b", r"needs?\b",
    r"must (?:obtain|provide|supply|upload|send)", r"gated on\b", r"waiting (?:for|on)\b",
)
# Markdown prose wraps, so a tombstone marker frequently sits on a neighbouring
# line.  Judging a line in isolation is how a guard ends up flagging its own
# supersession banner; evaluate a small window instead.
CONTEXT_BEFORE = 2
CONTEXT_AFTER = 2


def _hits(patterns, text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _enclosing_clause(line: str, position: int) -> str:
    """The table cell (or sentence) containing ``position``.

    Markdown rows carry several independent verdicts; a negation in a later cell
    says nothing about a requirement in an earlier one.
    """
    if line.count("|") >= 2:
        start = line.rfind("|", 0, position) + 1
        end = line.find("|", position)
        return line[start: end if end != -1 else len(line)]
    start = max(line.rfind(". ", 0, position) + 1, 0)
    end = line.find(". ", position)
    return line[start: end + 1 if end != -1 else len(line)]


def scan_line(rel: str, line: str, context: str = "") -> str | None:
    """Return a failure reason, or None when the line is acceptable.

    ``context`` is the surrounding window; tombstone markers count from it,
    while the forbidden phrase and its requirement grammar are read from the
    line itself.
    """
    window = context or line
    patterns = list(FORBIDDEN)
    if rel in TAG_SCOPED_PATHS:
        patterns.append(TAG_PATTERN)
    elif rel in MIXED_VENDOR_PATHS and re.search(TAG_PATTERN, line):
        if not _hits(NON_TUSHARE_MARKERS, line):
            patterns.append(TAG_PATTERN)

    hit = next(
        (m for m in (re.search(p, line, re.IGNORECASE) for p in patterns) if m), None
    )
    if hit is None:
        return None
    matched = hit.re.pattern
    # Judge the CLAUSE that carries the phrase, not the whole row: a markdown
    # table row often ends with an unrelated cell whose prose ("structurally
    # cannot answer ...") would otherwise excuse a live requirement sitting two
    # cells earlier.
    clause = _enclosing_clause(line, hit.start())
    # A prohibition is the opposite of a resurrection, even though it uses the
    # same nouns and often the word "required".
    if _hits(NEGATION, clause):
        return None
    if _hits(REQUIREMENT, clause):
        if _hits(STRONG_TOMBSTONE, clause) or _hits(STRONG_TOMBSTONE, window):
            return None
        return (
            f"active TuShare licensing requirement ({matched}); a requirement "
            "phrase needs an explicit NULL/SUPERSEDED/HISTORICAL tombstone"
        )
    if _hits(WEAK_TOMBSTONE, clause) or _hits(WEAK_TOMBSTONE, window):
        return None
    return f"un-tombstoned TuShare license-document reference ({matched})"


def main() -> int:
    failures: list[tuple[str, int, str, str]] = []
    missing: list[str] = []
    for rel in GUARDED_PATHS:
        path = REPO / rel
        if not path.is_file():
            missing.append(rel)
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            window = "\n".join(
                lines[max(0, index - CONTEXT_BEFORE): index + CONTEXT_AFTER + 1]
            )
            reason = scan_line(rel, line, window)
            if reason:
                failures.append((rel, index + 1, reason, line.strip()[:160]))

    for rel in missing:
        # A guarded surface that vanished is itself a finding: the guard must
        # never silently pass because its inputs disappeared.
        print(
            f"::error title=tushare-compliance-guard::guarded path is missing: {rel}",
            flush=True,
        )
    for rel, number, reason, excerpt in failures:
        print(
            f"::error title=tushare-compliance-guard::{rel}:{number}: {reason} — {excerpt}",
            flush=True,
        )

    if failures or missing:
        print(
            f"tushare-compliance-guard: {len(failures)} active reference(s), "
            f"{len(missing)} missing path(s) across {len(GUARDED_PATHS)} guarded surfaces",
            flush=True,
        )
        return 1
    print(
        f"tushare-compliance-guard: clean — {len(GUARDED_PATHS)} active authority "
        "surfaces carry no live TuShare license-document requirement",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
