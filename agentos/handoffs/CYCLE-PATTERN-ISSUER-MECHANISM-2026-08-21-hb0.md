---
workstream: "WS:CYCLE-PATTERN-ISSUER-MECHANISM"
session: claude/imce-hb-0-homebuilder-census
model: fable
ended_because: complete
mission: >
  A3 / IMCE-HB-0: build the frozen, reproducible homebuilder source and definition
  census that the merged IMCE-00 architecture freeze authorizes — roster and identity,
  denominator crosswalk, fiscal→calendar re-key, structural-break ledger, survivorship
  census, per-source vintage audit, hardened independent-block list, and exact A4
  cell-budget inputs. Records only. Stop before any fitting or outcome inspection.
state_before: >
  PR #6127 (IMCE-00 architecture freeze) merged 2026-08-21T03:55Z as ec44ae7d1659,
  releasing the HOLD-FOR-SOL and authorizing waves A1–A4. No HB-0 artifact existed.
  The freeze's own handoff recorded two debts owed specifically by this wave: the named
  survivorship census (§7.2 condition 5 / G8-B4) and the per-source vintage audit
  (§8 rider / G8-M6). The G4 homebuilder census figures (5–7 blocks, "three cancellation
  denominators", fully public-source) were adjudicated judgments never re-verified against
  primary filings — listed as `unverified` in that handoff.
changed:
  - path: research/imce/hb0/IMCE_HB0_CENSUS_FREEZE.md
    what: >
      NEW — the census freeze index: artifact map, acceptance-criteria audit, what changed
      relative to the freeze's expectations, fence-compliance proof, what is frozen, and
      the two corrections proposed-not-applied.
  - path: research/imce/hb0/IMCE_HB0_COHORT_IDENTITY_CENSUS.md
    what: >
      NEW — six identity passports with EDGAR-verified CIKs, name lineage (three roster
      members renamed inside/near the window), five named identity traps, structural roles
      (m=5 general, m=4 cancellation), and the LEN-exclusion correction C1.
  - path: research/imce/hb0/IMCE_HB0_METRIC_DEFINITION_CROSSWALK.md
    what: >
      NEW — the centerpiece. Six mutually incompatible cancellation-rate regimes; 14 named
      cross-issuer incompatibilities preserved (X1–X14); the late-era denominator finding
      that restricts cancellation cells to blocks 3–5; era-correlated disclosure hazard
      extended beyond LEN.
  - path: research/imce/hb0/IMCE_HB0_FISCAL_CALENDAR_MAP.md
    what: >
      NEW — six FYEs verified from cover pages AND 65 quarter-ends each; quarter→month map;
      three alignment hazards including a full-quarter zero-overlap case under identical
      fiscal labels; release lags from 144 issuer-quarters; metric-level available_at.
  - path: research/imce/hb0/IMCE_HB0_SOURCE_PIT_VINTAGE_MATRIX.md
    what: >
      NEW — the §8 vintage rider discharged. 17 series across 12 agencies; the five census
      vintage classes adjudicated as an HB-0-local vocabulary with a fixed crosswalk to the
      three-value CPI pit_class (no new enum minted); NAR storage bar; Treasury CMT as the
      only clean rate leg; the Census NRS first-print-archive upgrade path.
  - path: research/imce/hb0/IMCE_HB0_SURVIVORSHIP_CENSUS.md
    what: >
      NEW — §7.2 condition (5) discharged. 16 named mortality cases, 14 with EDGAR documents;
      the terminal-year blind spot; identity continuity resolved/unresolved; explicit
      inclusion decision (roster unchanged) with the disclosure retained and its text frozen;
      the second-order finding that four full-window survivors including the two most
      distressed are excluded.
  - path: research/imce/hb0/IMCE_HB0_STRUCTURAL_BREAK_LEDGER.md
    what: >
      NEW — 28 dated events; the universal no-restatement rule (acquisition-method +
      modified-retrospective) and its single exception (PHM FY2009 community-count reset,
      which DID recalculate); counts-vs-level breaks; block-grid collisions.
  - path: research/imce/hb0/IMCE_HB0_INDEPENDENT_BLOCK_LIST.md
    what: >
      NEW — the frozen block list audited against five admissibility conditions for the first
      time; five defects found; B hardened to 5; DEFF sensitivity grid; the ~87×
      pseudoreplication ceiling; come-back arithmetic reproducing the freeze's ~2145 only at B=5.
  - path: research/imce/hb0/IMCE_HB0_A4_CELL_BUDGET_INPUTS.md
    what: >
      NEW — exact A4 inputs; the finding that two of four D5 mechanism states have no
      cohort-wide measurable basis; per-cell-class effective-block arithmetic; ten mandatory
      conditions; six open elections A4 must make.
  - path: research/imce/hb0/IMCE_HB0_BLOCKERS_AND_FALSIFIERS.md
    what: >
      NEW — 7 hard blockers, 12 soft, 19 falsifiers grouped by conclusion attacked, 3 likely
      misreadings pre-empted, and the two corrections owed upward.
  - path: research/imce/hb0/evidence/*.md
    what: >
      NEW — seven research-lane packets preserved verbatim with a provenance header, carrying
      the full ~21-metric × 12-field tables per issuer, the 144-row release-lag table, the
      28-row break ledger and the 17-row vintage matrix, each with its own VERIFIED /
      SOURCE CLAIM / INFERENCE tiering and gaps table.
  - path: agentos/discoveries/DSC-FAILING-ISSUERS-STOP-FILING-BEFORE-COLLAPSE.md
    what: NEW — the terminal-year blind spot as a reusable survivorship landmine.
  - path: agentos/discoveries/DSC-NAR-TERMS-BAR-STORAGE-NOT-ONLY-REDISTRIBUTION.md
    what: NEW — housing-source rights constraints; rights gate precedes vintage gate.
  - path: agentos/discoveries/DSC-EDGAR-STRUCTURED-ISSUER-METADATA-IS-UNTRUSTWORTHY.md
    what: NEW — corrupted period-of-report and Form-15 scope, both measured.
  - path: agentos/discoveries/DSC-HOMEBUILDER-CANCELLATION-DENOMINATORS-ALL-DIVERGE.md
    what: NEW — six regimes, no shared denominator, late-era only.
  - path: agentos/workstreams/WS-CYCLE-PATTERN-ISSUER-MECHANISM.md
    what: IMCE-00 status healed to done (merged); A3 marked done with its next_action.
verified:
  - claim: "PR #6127 merged and is the exact commit this wave builds on"
    command: "gh pr view 6127 --json state,mergedAt,mergeCommit; git rev-parse origin/main"
    result: "MERGED 2026-08-21T03:55:28Z; mergeCommit == origin/main == ec44ae7d1659"
  - claim: "All six roster CIKs are correct"
    command: "EDGAR browse-edgar company search per ticker, run independently of the census lane"
    result: "DHI 882184, LEN 920760, PHM 822416, NVR 906163, KBH 795266, TOL 794170 — lane agrees"
  - claim: "The freeze's ~2145 come-back headline reproduces only at B=5"
    command: "python3 arithmetic over span 2006→2023 (first block start → last CLOSED block end), floor 40"
    result: "B=5 → ~2146; B=6 → ~2123; B=7 → ~2124. Freeze states ~2145."
  - claim: "No outcome, price or FRED content appears in any artifact or packet"
    command: "grep -rinE 'stock price|share price|total return|market cap|closing price|p-value' + grep -rio 'fred\\.stlouisfed|alfred' over research/imce/hb0/"
    result: "Only the fence declarations themselves and prohibition references. Zero substantive hits."
  - claim: "agentos records validate"
    command: "python3 scripts/agentos.py validate"
    result: "451 records, 0 errors (22 pre-existing warnings, none in new files)"
  - claim: "CPI pit_class enum has three values, not the five the commission named"
    command: "read config/cycle_pattern/truth_schema.md:61-67"
    result: "pit_pure / revision_optimistic / mixed — hence the HB-0-local vocabulary + crosswalk"
unverified:
  - claim: "Field 12 (earliest lawful historical coverage) for every metric × issuer"
    what_would_verify: >
      Opening all 22 years × 6 issuers of 10-Ks. The lanes opened a representative spine
      (FY2005, FY2009/10, FY2016, FY2024/25 + press releases); everything else is typed
      `missing`/`not_reconstructable`, never interpolated. The DHI/LEN lane returned PARTIAL
      for exactly this reason.
  - claim: "Whether pre-2016 PHM/NVR cancellation METHODOLOGY differed, or only the prose"
    what_would_verify: "efts.sec.gov full-text search of PHM/NVR 10-Ks FY2006-FY2015 for the formula sentence"
  - claim: "Six rights/revision verdicts (MBA, S&P DJI, BLS CPI, NAHB terms)"
    what_would_verify: >
      Re-opening the agency pages, which returned HTTP 403 to the fetch tool. These are
      labelled SOURCE CLAIM in the matrix. NAHB is UNVERIFIED, not cleared.
  - claim: "Metric-level available_at for five of six issuers"
    what_would_verify: "Open one EX-99.1 + matching 10-Q/10-K per issuer and diff line items; done for DHI only (1 of 144)"
  - claim: "Fleet-wide accounting-standard adoption dates for PHM/NVR/KBH/TOL individually"
    what_would_verify: "Open each issuer's ASC 606/842/CECL adoption note; VERIFIED for DHI and LEN only, INFERENCE for the rest"
unresolved:
  - "C1 and C2 corrections are PROPOSED, not applied — they amend a merged freeze condition and the frozen block list, which needs Fable/Sol adjudication and an amendment-log entry"
  - "Two of four D5 mechanism states (completed_inventory_build, pace_recovery) have no cohort-wide measurable basis — A4 must re-scope or drop those cells before the budget can be populated"
  - "TOL requires an explicit election between its two published cancellation denominators"
  - "Freddie Mac PMMS rights ambiguity — HELD, needs a determination before it can be a stored leg"
  - "A2 (CPI truth-contract audit) still must land before any issuer truth is appended — unchanged by this wave"
next_actions:
  - "Fable/Sol adjudicate C1 (restate the LEN exclusion's reason) and C2 (block list → B=5) as amendment-log entries"
  - "A4 (IMCE-03) makes the six elections in IMCE_HB0_A4_CELL_BUDGET_INPUTS.md §8 before any criteria commit"
  - "A1 (CELH autopsy) and A2 (CPI audit) remain authorized and independent of this wave"
  - "Optional, costed and not executed: upgrade Census NRS to pit_pure by parsing its first-print release archive (back to Jan 1995)"
do_not_redo:
  - "The seven HB-0 evidence lanes — packets are preserved verbatim under research/imce/hb0/evidence/ with their own gaps tables naming exactly what each lane did not verify. Re-verify only what a moved main or a named falsifier invalidates."
  - "The DEFF sensitivity grid — ρ is deliberately NOT estimated here; estimating it requires train folds and belongs to A4, not to a census"
  - "The roster question — the inclusion decision is recorded with reasons; re-open it only via an amendment-log entry, and never after outcome inspection (freeze D6)"
  - "Do not re-derive the block count from the frozen list's literal seven entries; the overlap and open-block defects are documented"
danger_areas:
  - "Widening the roster to MTH/MHO/BZH/HOV improves representativeness and adds NO power — at ρ≈0.8, m=6→10 moves n_eff from ~6.0 to ~6.2. Treating it as a power fix is the most tempting error available here."
  - "n_effective_blocks as computed is an UPPER BOUND — the DEFF rule handles within-block issuer correlation and says nothing about between-block serial dependence"
  - "NAR data may not be STORED at all — this is an ingestion bar like FRED clause (q), not a redistribution clause a private database escapes"
  - "TOL's 'Net Signed Contracts' nets cancellations of PRIOR-period contracts into the current period — it is a different formula from peer net orders, not a different level"
  - "Reading TOL's FY2023 'spec homes' terminology onset as a FY2023 strategy change manufactures an event out of a disclosure choice; TOL's unhyphenated 'speculative homes' appears from FY2006"
  - "underpowered_accruing is a Research-Factory status ONLY and may never enter the CPI registry without a schema + consumer-matrix amendment [G8-M7]"
prs: []
decisions: []
---

# Production proof state

**Not owed — records only.** This wave writes only under `research/imce/hb0/` and `agentos/`.
No `engine/`, `scripts/`, `app/`, `collectors/`, `site/`, `templates/`, `data/`, `.github/` or
test path is touched. No runtime, no data plane, no trial-ledger row, no UI.

# For the cold stranger

The homebuilder family was promoted by IMCE-00 as the program's **first quantitative family**.
This census qualifies that promotion without withdrawing it.

What held: the roster is workable, the sources are public, the fiscal crosswalk is
constructible, and the honest block count sits inside the freeze's stated 5–7 range.

What did not: the signature homebuilder metric (cancellation rate) has six mutually
incompatible definitions and **no verifiable denominator in the two GFC-era blocks**; two of
the four mechanism states in the D5 vector have **no cohort-wide measurable basis at all**;
and the roster is survivor-selected in two independent senses, one of which (the terminal-year
blind spot) cannot be repaired by adding the dead companies back.

Every correction this census made to its own inputs **reduced** the numbers — B from 7 to 5,
n_eff to the bottom of its range, the cancellation cell from 5 blocks to 3. None created
headroom. The predetermined `underpowered_accruing` status is therefore confirmed on this
census's own arithmetic rather than inherited from the freeze, and the come-back date
(~2146 at B=5) independently reproduces the freeze's published ~2145 headline.

**A3 stops here.** A4 owns the first `data/` write and must make six named elections first.
