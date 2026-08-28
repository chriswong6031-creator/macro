# TFG-1 R3 — Deterministic Transcript-Format Hardening (implementation packet)

**Status:** `NOT_BUILT`. This is the sole active implementation packet for the successor wave.
**Operation key (successor, not started):** `tfg1-r3-deterministic-transcript-format-hardening-20260828-v1`
**Predecessor:** `tfg1-r2-deterministic-transcript-format-hardening-20260827-v1` — terminal,
`STOPPED_AT_DEVELOPMENT_GATE — SECOND GOLD FALSIFIER`, PR #6591 CLOSED UNMERGED.
**Grading truth:** `research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r3.json`
**Governing decision:** `DEC:E3FMT-DEVELOPMENT-GOLD-R3-RESPONDENT-ROLE-SOURCE-CLEAN`

This packet does not commission the wave. A distinct Sol commission with its own carrier is required.

## §0 Acceptance gates — not done unless

1. 113/113 structural separators recovered, zero opening/queue/closing false positives.
2. 103/103 source-supported questioners resolved — 97 direct, 6 explicit full-name proxy.
3. 10/10 unresolved questioner handoffs preserved as separator-only refusals, zero adjacent contamination.
4. **All 7** source-clean calls produce non-empty full-call reconstruction.
5. **All 9** refusing calls fail for their frozen blocker **SET**, not a single first-failure reason.
6. AAPL exact: 7 exchanges / 26 management answer turns / 68 replay spans, plus mutated-SHA refusal.
7. Accepted-unsupported = 0, cross-event contamination = 0, accepted replay = 100%.
8. Zero model calls in the structural or identity path. No ticker or provider branch.

Any source-clean call failing, any separator precision/recall miss, or any need for guessed/external
identity is terminal: **STOP and return the falsifier. Do not rescue.** That instruction has now
produced two genuine findings; it is the working mechanism of this program, not boilerplate.

## §1 Ratified development truth

```
structural separators            113
direct questioners                97
explicit full-name proxies         6
source-supported questioners     103
unresolved questioners            10
management-role-conflict calls     5   ARRY, CTRE, BANR, LTH, HTGC
missing-role-support calls         2   ARQQ, FANG
source-clean full calls            7   OCSL/2026Q3, GEF/2026Q3, UPBD/2026Q2,
                                       SCCO/2026Q2, AGM/2026Q2, COF/2026Q2, KREF/2026Q2
refusal calls                      9   MBLY, ARQQ, TRVI, CTRE, LTH, BANR, FANG, HTGC, ARRY
```

Per-call blocker sets are authoritative in the R3 JSON. Do not re-derive them from prose.

## §2 The source-clean definition — read this twice

A call is `QNA_SOURCE_CLEAN` only when **every** management answer that would be accepted into
`qa_exchange.v1` has **positive replayable same-revision** respondent role/title support, **and**
carries no incompatible same-revision role evidence.

**Absence of role conflict is NOT source-clean.** The prior definition tested only for contradiction
and therefore could not see a speaker with no role evidence at all — which is exactly how ARQQ and
FANG were admitted to a set they cannot satisfy. Write the check as a positive support requirement.

## §3 Blockers are sets

Record every blocker a call's exact revision supports. CTRE, LTH, BANR and HTGC each carry
`unresolved_questioner` **and** `management_role_conflict` simultaneously. An order-dependent single
first-failure reason hides the others behind whichever the implementation happens to evaluate first,
so a correct and an incorrect implementation emit the same receipt. That is what produced the first
falsifier.

## §4 Holdout law — unchanged in structure, corrected in definition

Ranks 17–24 remain **SEALED**. `holdout_bodies_inspected: 0` across all three waves so far.

1. No holdout body, speaker metadata, Operator text or derived feature may be fetched before every
   development gate is green and the exact implementation head SHA + timestamp are frozen.
2. After freeze, **no code changes are permitted** — not before the unseal, not after it.
3. Byte-replay the exact 8 revisions.
4. **Before any compiler output**, freeze `tfg1.holdout_source_adjudication.v1` per slot as one of
   `QNA_SOURCE_CLEAN | QNA_SOURCE_CONFLICTED | NO_QA_ADMISSION | SOURCE_REVISION_MISMATCH`, using the
   corrected positive-role-support definition in §2.
5. `<6/8` source-clean ⇒ STOP `INSUFFICIENT_HOLDOUT_POWER`. No replacement, skip or rerank.
6. If powered, run the frozen compiler once. Every source-clean slot must produce non-empty full-call
   reconstruction; conflicted slots preserve separators and fail only their pre-adjudicated reason;
   no-QA slots create zero false boundaries.
7. Any holdout miss is terminal for that implementation. Do not patch and retest the same holdout.
8. GOOGL runs only after freeze, as a spent-falsifier regression. It can never be fresh OOS clearance.

## §5 Scope

**Expected surface:** `engine/company_intelligence/qa_reconstruction.py`,
`engine/company_intelligence/qa_exchange.py`, existing Q&A tests, one focused R3 test module, and at
most one private helper under `engine/company_intelligence/` if clearly internal to this compiler.

**Do not touch:** `event_workspace.production_registry()` / Alphabet registration;
`scripts/refresh_event_workspaces.py` production coverage; the accepted AAPL-only production revision
admission; Terminal repo/UI; source acquisition or provider selection; the event/company identity
plane; any new Q&A/person/transcript/candidate store; model routing;
FIF/Prophet/scoring/sentiment/beat-miss/rank-size-gate-trade; CAT/BAC/SNOW bodies; E3-OOS2; E3-P.

**Closed candidates, evidence only:** PR #6591 (`77fd9411c9cf`) and PR #6602 (`8078d54ba892`) are both
CLOSED UNMERGED. Their branches are preserved. Do not reopen, merge, force-push, or cherry-pick them
wholesale. #6591 in particular contains a working structural implementation that scored fully green on
the structural half — it is legitimate to read as candidate evidence and illegitimate to treat as
accepted truth.

## §6 Method

Strict RED → GREEN. No production behavior change before a discriminator test is written and observed
failing for the intended missing behavior; preserve the RED receipt.

Required RED discriminators, in addition to those carried forward from R1/R2:

- a management answer with **no** same-revision role/title support refuses, and its call leaves the
  source-clean set — the ARQQ/FANG case, which no prior discriminator covered;
- a refusing call emits **every** applicable blocker, and a mutant that returns only the first
  blocker is killed;
- the five role-conflict calls are all detected, and a relaxation that recovers only ARRY and CTRE is
  killed;
- opening/prepared-speaker "go ahead" handoffs still rejected; multiple terminal dialects still work
  without cue-phrase authority; punctuation-safe affiliations; exact CEO/CFO/COO alias map with the
  `CIO` mutation killed; external/fuzzy inference mutant killed.

## §7 Known traps

- **Transcript body SHAs are canonical-JSON hashes**, not sha256 of the raw decompressed body. 15 of
  16 development files happen to be canonical so both conventions agree; `COF/2026Q2` does not, and
  the raw convention falsely reports it as a moved revision. See
  `DSC:TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES`.
- **The obvious branch name is taken.** `claude/tfg1-r3-gold-source-clean-correction` belongs to the
  closed #6602 candidate and exists on the remote; on this shared clone it is also present locally.
- **AAPL is undisturbed by construction only while `engine/` is untouched.** Once the compiler changes,
  7/26/68 must be re-proven, not assumed.

## §8 Return

`DRAFT / HOLD-FOR-SOL`, classification `BUILT_NOT_PROVEN` only if development **and** the single-use
holdout both pass; otherwise the exact named falsifier or blocker. Do not merge. Do not start E3-OOS2
or E3-P. R3 passing does not close E3-C.
