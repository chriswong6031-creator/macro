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

TWO TIERS, because they fail differently:

* ``FORBIDDEN`` is the license-document MECHANISM as a noun ("vendor letter",
  "authorization receipt").  An ordinary prohibition anywhere in the clause
  excuses it, because "no vendor letter is required" is exactly how the
  supersession has to be written.
* ``FORBIDDEN_INSTRUCTION`` is a DIRECTIVE to go obtain vendor approval ("ask
  the vendor in writing", "vendor must confirm", "until the vendor confirms").
  An ordinary prohibition does NOT excuse it.  In "still do not buy until the
  vendor confirms named-actor commercial use" the negation governs *buy* while
  the vendor step stays live -- that sentence sat in the guarded rights matrix
  and passed the first version of this guard.  Only a prohibition that DIRECTLY
  governs the instruction, or a strong tombstone in the SAME clause, clears it.

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
    # Handoffs are HISTORY and are deliberately not guarded as a class -- but a
    # workstream's CURRENT handoff is not only history: AgentOS treats its
    # `do_not_redo` and `next_actions` as binding on the next session.  This one
    # still told that session to "send Tushare the five questions" and that
    # "rights questions go to a vendor letter".
    "agentos/handoffs/TUSHARE-ENTITLEMENT-2026-08-19.md",
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
)

# Rights-row labels as they are actually spelled across the registries.  The
# first verdict cell after one of these labels is the TuShare route in every
# guarded table -- native/Eastmoney/SZSE columns sit further right and keep
# their own UNKNOWN verdicts, which this override does not touch.
_RIGHTS_LABEL = (
    r"(?:Raw redistribution"
    r"|Product-display rights"
    r"|Persistence(?:\s*/\s*derived-use)?(?:\s*/\s*display)?(?:\s+rights)?"
    r"|Derived[ -](?:model/display|use)(?:\s*/\s*display)?(?:\s+rights)?)"
)
# The bare verdict-cell shape Sol flagged: "| Derived model/display | UNKNOWN".
# Spelled out for every label so the guard is not narrower than the threat --
# three `Persistence rights | UNKNOWN` rows survived the first pass because the
# label list only carried four of the eight spellings in use.
FORBIDDEN += (rf"\|\s*{_RIGHTS_LABEL}\s*\|\s*UNKNOWN",)

# The addressee, however it is spelled.  Naming the vendor instead of using the
# word "vendor" is the same instruction: WS-TUSHARE-ENTITLEMENT's `next_action`
# read "asks Tushare in writing the five commercial questions" and sailed
# through the first version of this guard for exactly that reason.
_VENDOR = r"(?:the )?(?:vendor|tushare(?:\.pro)?)"

# Directives to go obtain vendor approval.  Cleared only by a DIRECTLY governing
# prohibition or a strong tombstone in the same clause -- see the tier note above.
FORBIDDEN_INSTRUCTION = (
    # Asking the vendor for PERMISSION, not asking it for data: "asking the
    # vendor for <trade dates>" is an ordinary collector docstring, so the ask
    # has to carry a permission-shaped object to count.
    rf"\bask(?:s|ing|ed)? {_VENDOR}\s+(?:in writing|whether|if\b|about|to confirm"
    r"|to approve|to clarify|for (?:permission|confirmation|approval|clearance"
    r"|a letter|a written|written|sign-?off))",
    rf"\bask(?:s|ing|ed)? {_VENDOR}\s*:",
    rf"\b(?:confirm|clarify|verify|check|raise) (?:with|from|via|to) {_VENDOR}\b",
    rf"\b{_VENDOR} (?:confirms?|confirmed|confirming)\b",
    rf"\b{_VENDOR} (?:must|should|shall|will|needs? to|has to|is to|to) "
    r"(?:confirm|approve|agree|sign|answer|clarify|respond|say)\b",
    # "until the vendor CONFIRMS", not the bare "until the TuShare spine exists":
    # the approval verb is what makes it a compliance precondition.
    rf"\buntil {_VENDOR} (?:confirms?|approves?|agrees?|says|answers|responds"
    r"|clarifies|signs|grants?)\b",
    rf"\b{_VENDOR}[- ](?:confirmation|approval|sign-?off|yes|answer)\b",
    rf"\bin writing (?:to|from|with) {_VENDOR}\b",
    rf"\b(?:asks?|asking|put|puts|putting) {_VENDOR} in writing\b",
    r"\bwritten (?:enquiry|inquiry|question)s? (?:to|for) (?:the )?(?:vendor|tushare)\b",
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
#
# `do not` is deliberately ABSENT.  It used to be here, and it is what let "still
# do not buy until the vendor confirms named-actor commercial use" pass: that
# negation governs *buy*, not the vendor step.  A bare `do not` now counts only
# through GOVERNING_PROHIBITION, which makes it sit directly in front of the
# phrase it is supposed to be cancelling.
NEGATION = (
    r"\bno (?:vendor|written|authorization|reintroduced|license|such|longer)\b",
    r"\bnot required\b", r"\bnever\b", r"\bmust not\b", r"\bmay not\b",
    r"\bcannot\b", r"\bforbidden\b", r"\bprohibit", r"\brefus",
    r"\bremoved\b", r"\bnulls?\b", r"\bthe former\b", r"\brenamed\b",
    r"\bhistorical\b", r"\bsuperseded\b", r"\bcancelled\b", r"\bformerly\b",
)
# A prohibition that DIRECTLY governs the phrase: immediately in front of it,
# allowing at most one adverb.  "never ask the vendor" clears; "do not buy until
# the vendor confirms" does not, because `buy until` sits in between.
#
# The second alternative is the negated-SUBJECT shape ("No coding session may ask
# the vendor ..."), which is a real prohibition even though the negative word is
# three tokens back.  It still requires a modal immediately before the phrase, so
# "do not buy until ..." cannot reach it.
GOVERNING_PROHIBITION = re.compile(
    r"(?:"
    r"(?:\bnever|\bnot|\bno|\bno longer|\bmay not|\bmust not|\bcannot|\bcan't|"
    r"\bdo(?:es)? not|\bdid not|\bwithout|\bstops?|\bstopped)\s+(?:\w+ly\s+)?"
    r"|"
    r"\bno\b(?:\s+\w+){0,3}\s+(?:may|can|shall|will|should|is to|are to|needs? to)\s+"
    r")$",
    re.IGNORECASE,
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
# Markdown PROSE wraps, so a tombstone marker frequently sits on a neighbouring
# line.  Judging a line in isolation is how a guard ends up flagging its own
# supersession banner; evaluate a small window instead.
#
# A markdown TABLE row does not wrap.  Each cell is an independent verdict, so a
# marker in a different cell -- let alone a different row two lines away -- says
# nothing about this one.  Table lines therefore keep the clause as their entire
# tombstone scope; only prose gets the window.
CONTEXT_BEFORE = 2
CONTEXT_AFTER = 2


def _hits(patterns, text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _is_table_row(line: str) -> bool:
    return line.count("|") >= 2


def _clause_span(line: str, position: int) -> tuple[int, int]:
    """Bounds of the table cell (or sentence) containing ``position``.

    Markdown rows carry several independent verdicts; a negation in a later cell
    says nothing about a requirement in an earlier one.
    """
    if _is_table_row(line):
        start = line.rfind("|", 0, position) + 1
        end = line.find("|", position)
        return start, end if end != -1 else len(line)
    start = max(line.rfind(". ", 0, position) + 1, 0)
    end = line.find(". ", position)
    return start, end + 1 if end != -1 else len(line)


def _enclosing_clause(line: str, position: int) -> str:
    start, end = _clause_span(line, position)
    return line[start:end]


def _tombstone_scope(line: str, clause: str, window: str) -> str:
    """Where a tombstone marker may legitimately live for this line."""
    return clause if _is_table_row(line) else window


def _first_match(patterns, line: str):
    return next(
        (m for m in (re.search(p, line, re.IGNORECASE) for p in patterns) if m), None
    )


def scan_line(rel: str, line: str, context: str = "") -> str | None:
    """Return a failure reason, or None when the line is acceptable.

    ``context`` is the surrounding window; for PROSE lines tombstone markers may
    come from it, while the forbidden phrase and its requirement grammar are
    always read from the line itself.
    """
    window = context or line
    patterns = list(FORBIDDEN)
    if rel in TAG_SCOPED_PATHS:
        patterns.append(TAG_PATTERN)
    elif rel in MIXED_VENDOR_PATHS and re.search(TAG_PATTERN, line):
        if not _hits(NON_TUSHARE_MARKERS, line):
            patterns.append(TAG_PATTERN)

    hit = _first_match(patterns, line)
    if hit is not None:
        # Judge the CLAUSE that carries the phrase, not the whole row: a markdown
        # table row often ends with an unrelated cell whose prose ("structurally
        # cannot answer ...") would otherwise excuse a live requirement sitting
        # two cells earlier.
        start, end = _clause_span(line, hit.start())
        clause = line[start:end]
        scope = _tombstone_scope(line, clause, window)
        matched = hit.re.pattern
        # A prohibition is the opposite of a resurrection, even though it uses
        # the same nouns and often the word "required".
        if _hits(NEGATION, clause):
            return None
        if GOVERNING_PROHIBITION.search(line[start:hit.start()]):
            return None
        if _hits(REQUIREMENT, clause):
            if _hits(STRONG_TOMBSTONE, clause) or _hits(STRONG_TOMBSTONE, scope):
                return None
            return (
                f"active TuShare licensing requirement ({matched}); a requirement "
                "phrase needs an explicit NULL/SUPERSEDED/HISTORICAL tombstone"
            )
        if _hits(WEAK_TOMBSTONE, clause) or _hits(WEAK_TOMBSTONE, scope):
            return None
        return f"un-tombstoned TuShare license-document reference ({matched})"

    order = _first_match(FORBIDDEN_INSTRUCTION, line)
    if order is None:
        return None
    start, end = _clause_span(line, order.start())
    clause = line[start:end]
    # No ordinary-negation escape here: only a prohibition sitting directly in
    # front of the instruction, or an explicit tombstone in the SAME clause.
    if GOVERNING_PROHIBITION.search(line[start:order.start()]):
        return None
    if _hits(STRONG_TOMBSTONE, clause):
        return None
    return (
        f"active TuShare vendor-approval instruction ({order.re.pattern}); "
        "compliance is CHAIRMAN_VERIFIED_PRIVATE / SATISFIED and may not be "
        "reopened -- state an engineering/access/build state, or wrap the "
        "historical wording as NULL/SUPERSEDED"
    )


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
