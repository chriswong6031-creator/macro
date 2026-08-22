---
workstream: "WS:CYCLE-PATTERN-ISSUER-MECHANISM"
session: claude/imce-a1-celh-cycle-autopsy
model: opus
ended_because: complete
mission: >
  IMCE wave A1 (IMCE-CELH-1): produce the records-only CELH Cycle Autopsy 2018-2026 —
  source chronology, three-clock timeline, mechanism epochs, fixed recognition telemetry
  under ONE named construction, source/rights/missingness ledger, falsifier list, and a
  proposed (not activated) prospective observation registration. Zero outcome
  computation. Stop at the research packet; return to Fable.
state_before: >
  IMCE-00 freeze PR #6127 merged 2026-08-21T03:55:28Z as ec44ae7d1659 and was the tip of
  origin/main, releasing the HOLD-FOR-SOL and thereby authorizing A1-A3. No CELH research
  artifact existed in the repo — the G1/G2 census CONCLUSIONS were summarized in the
  freeze but their evidence rows were never committed, so A1 had to build the receipted
  chronology from primary sources rather than re-reading a stored packet.
changed:
  - path: research/imce/CELH_CYCLE_AUTOPSY_2018_2026.md
    what: >
      NEW — the autopsy: evidence discipline, 8 mechanism epochs with clock-stamped
      boundaries, operating/translation/recognition clock narratives, the sell-in vs
      sell-through wedge series with its comparability warnings, the named 2W
      construction and its 16 in-window cross events, a three-clock table at every phase
      transition, the ten commissioned questions answered descriptively, and the
      executive note to Fable.
  - path: research/imce/celh/celh_evidence_chronology.csv
    what: NEW — 52 rows, each with clock/epoch/event_time/measurement window/available_at/retro lag/evidence class/accession/URL/missingness.
  - path: research/imce/celh/celh_mechanism_epochs.csv
    what: NEW — 8 epochs (M0, M0a, M1-M6) with boundary_class, BOTH clock dates, lag, receipt, and comparability break.
  - path: research/imce/celh/celh_three_clock_state.csv
    what: NEW — 18 quarters x 27 columns; the three clocks kept as separate column families, never collapsed.
  - path: research/imce/celh/celh_recognition_events.csv
    what: NEW — 33 completed-bar 2W cross events (16 in window). NO OUTCOME COLUMNS.
  - path: research/imce/celh/celh_2w_state_full.csv
    what: NEW — all 478 defined-histogram 2W bars (state, hist, sign, first difference).
  - path: research/imce/celh/celh_xbrl_original_disclosures.csv
    what: NEW — 655 rows; earliest-filed value per concept/period with a restatement flag (60 flagged).
  - path: research/imce/celh/celh_source_rights_missingness.csv
    what: NEW — 20 rows; every source used or wanted, its rights disposition, coverage achieved, and typed missingness.
  - path: research/imce/celh/celh_falsifiers_open_questions.md
    what: NEW — 7 mechanism hypotheses each with a NAMED falsifier and a competing explanation; overall-interpretation falsifiers; 7 open questions.
  - path: research/imce/celh/celh_prospective_observation_registration.yaml
    what: NEW — proposed prospective capture in three tiers (observable now / prospective-from-capture / unavailable). RECORDS ONLY, authority all false, NOT ACTIVATED.
  - path: research/imce/celh/celh_recognition_tape_2w.py
    what: >
      NEW — reproduction receipt for the recognition tables. NOT RUNTIME: nothing imports
      it, no engine/collector/workflow/page/nightly path calls it. It asserts histogram
      parity against engine.technicals.macd_hist and asserts that no outcome-shaped
      column name exists.
  - path: agentos/discoveries/DSC-ISSUER-EPOCH-BOUNDARY-LAG-SPLITS-BY-BOUNDARY-CLASS.md
    what: NEW — corporate-event boundaries lag ~0-4d; operating-action boundaries ~125-127d.
  - path: agentos/discoveries/DSC-ACCRUED-PROMO-ALLOWANCE-IS-INVISIBLE-TO-XBRL-COMPANYFACTS.md
    what: NEW — companyfacts omits issuer-custom lines; the nearest us-gaap concept understates by ~4x.
  - path: agentos/workstreams/WS-CYCLE-PATTERN-ISSUER-MECHANISM.md
    what: IMCE-00 awaiting_ci -> done (merge receipt); A1 todo -> done; status -> in_progress; next_action -> A2/A3; four new do_not_redo entries; A1 artifacts and discoveries listed.
  - path: agentos/handoffs/CYCLE-PATTERN-ISSUER-MECHANISM-2026-08-21.md
    what: NEW — this handoff.
verified:
  - claim: "PR #6127 merged and is the tip of origin/main (the A1 precondition)"
    command: "git fetch origin && git log --oneline -1 origin/main; gh pr view 6127 --json state,mergedAt,mergeCommit"
    result: "MERGED 2026-08-21T03:55:28Z, mergeCommit ec44ae7d16598c6285b3e6e1fde26ee176703cad == origin/main tip"
  - claim: "The Q1-2023 pipeline fill was NOT disclosed at decision time"
    command: "grep -c -i -E 'pipeline|days on hand|inventory buildup|inventory build-up' on the Q1-2023 10-Q text (accession 0000950170-23-019722)"
    result: "0 occurrences. The ~$25M characterization first appears in the 2024-05-07 release (0001341766-24-000031) — 364 days after the original filing."
  - claim: "Recognition telemetry uses ONE named house construction and computes no outcome"
    command: "python3 research/imce/celh/celh_recognition_tape_2w.py"
    result: >
      macd_hist parity assertion passes; 511 2W-FRI bars, 478 defined-histogram bars from
      2008-05-02 (26+9-bar warm-up), 33 cross events (16 bullish / 17 bearish), 16 in the
      2018+ window; outcome-column assertion passes.
  - claim: "Accounting-translation facts are first-disclosure values with exact available_at"
    command: "SEC XBRL companyfacts CIK0001341766; earliest-filed row per (concept,start,end,unit) with restatement flag"
    result: "655 original-disclosure rows written; 60 carry a differing later value and are flagged restated"
  - claim: "All packet CSVs are well-formed"
    command: "csv.reader column-count check across research/imce/celh/*.csv"
    result: "7 files, 0 mismatched rows (5 unquoted-comma defects found and fixed before commit)"
  - claim: "No forbidden outcome token and no CI-guarded 'validated' claim appears in the packet"
    command: "grep -rn -iE '<outcome tokens>' and grep -rn -i validated over research/imce/"
    result: "only the prohibition statements themselves match; zero 'validated' occurrences"
unverified:
  - claim: "The epoch-boundary lag CLASS SPLIT generalizes beyond CELH"
    what_would_verify: >
      Build the same operating-start vs available_at table for a second family with both
      boundary classes in-window (IMCE-HB-0 homebuilders is the natural test). The DSC is
      filed at confidence: probable for exactly this reason.
  - claim: "The wedge is a mechanism rather than partly a denominator artifact"
    what_would_verify: >
      One consistent Circana denominator across 2023-2026 — rights_blocked (CIRCANA_DIRECT
      is HOLD). Recorded as the open half of falsifier H1; the packet does not claim
      identification.
  - claim: "CELH's Data OS security_id"
    what_would_verify: "engine/company_intelligence/identity.py resolution; typed unresolved_identity in the packet (S018). Required before any Stock Identity Episode citation."
unresolved:
  - "U7 — is the 2026 assortment reset (M6) a distinct epoch or an operating phase inside M5? Recorded BOTH ways in celh_mechanism_epochs.csv; Fable adjudicates."
  - "U1 — does recognition lead/lag/track the mechanism at CELH? An outcome question; forbidden until the A4 criteria commit."
  - "A2 (CPI vocabulary audit) still gates ANY issuer truth append — nothing from A1 may enter the CPI registry before it lands."
  - "Whether the packet's Tier-1 prospective capture list should be activated, and by which wave — this file registers nothing."
next_actions:
  - "Fable: read §8 of the autopsy (executive note) and rule on U7."
  - "Commission A2 (CPI truth-contract audit, all 29 registry rows) and A3 (IMCE-HB-0 census freeze) — they may run in parallel."
  - "A3 should run the DSC epoch-lag test on homebuilders — it is a cheap second-family check that either promotes or breaks the class split."
  - "A4 only after A2+A3; criteria commit strictly before any outcome access."
do_not_redo:
  - "The CELH source chronology, epoch table, wedge series and 2W tape — delivered with accession-level provenance under research/imce/celh/."
  - "Do not attach outcome fields to celh_recognition_events.csv before the A4 criteria commit."
  - "Do not treat the CELH sell-through series as one measurement across 2023->2026 (three Circana denominators)."
  - "Do not read accrued promotional allowance from XBRL companyfacts, and never substitute AccruedMarketingCostsCurrent."
danger_areas:
  - "celh_recognition_events.csv is outcome-free BY CONTRACT. Adding a forward-return column there breaks the two-commit discipline (G8-B1) and the reproduction script's own assertion."
  - "Epoch operating-clock starts (M2 2024-01-01, M3 2025-01-01, M6 2026-04-01) are LOOK-AHEAD if used to partition a recognition statistic — use boundary_available_at (2024-05-07 / 2025-05-06 / 2026-08-06)."
  - "The 2W bin edges depend on the FULL price series start. Slicing data/yahoo/CELH.parquet before resampling silently changes every bar and every cross date."
  - "CELH is DESCRIPTIVE forever, 0 historical cells, barred by rule and not by count. Nothing here may be cited as evidence of issuer-specific forecast skill."
  - "The G2 census tape (which carried +21/+63-trading-day path fields) stays quarantined; this packet cites it nowhere and neither may a successor."
  - "Mechanism epochs M0-M6 are NOT identity epochs. identity_epoch remains not_yet_built (Stock Identity W4 todo); conflating them recreates the rival-epoch-stack violation (G8-M5)."
prs: []
decisions: []
discoveries:
  - "DSC:ISSUER-EPOCH-BOUNDARY-LAG-SPLITS-BY-BOUNDARY-CLASS"
  - "DSC:ACCRUED-PROMO-ALLOWANCE-IS-INVISIBLE-TO-XBRL-COMPANYFACTS"
---

# Production proof state

**Not owed — records only.** This wave touches `research/` and `agentos/` exclusively. No
`engine/`, `scripts/`, `app/`, `collectors/`, `site/`, `templates/`, `data/`, `.github/`
or test path is modified, so no render and no live verification is owed. The one `.py`
file added is a reproduction receipt under `research/`, consistent with the 160 existing
research-tier scripts in the repo; nothing imports it.

# For the cold stranger

The autopsy's one-sentence result: **CELH's reported revenue line is not a demand series
— its largest swings come from the gap between sell-in and sell-through, opened and
closed by one dominant customer's working-capital policy and by CELH's own trade
investment, and the market could not see the 2023 half of that mechanism until 364 days
after the fact.**

The three things most likely to be re-derived wastefully, and where they already are:

1. **The wedge series** (sell-in minus sell-through, by quarter, with the comparability
   warnings that make half the quarters unusable) — autopsy §4.2 and
   `celh_three_clock_state.csv`.
2. **The available_at backbone** (41 periodic filings + 22 earnings 8-Ks with accessions)
   — reproduce in one call from `https://data.sec.gov/submissions/CIK0001341766.json`.
3. **The retro-disclosure exhibit** (the 364-day lag and the reproducible zero-hit scan
   that proves the absence) — chronology rows E016/E017.

The single most transferable output is **not** the CELH narrative. It is the pair of
DSC records: epoch boundaries split into two classes with ~0-day and ~126-day recognition
lags, and `companyfacts` silently omits the issuer-custom line where trade investment
lives. Both apply to every issuer family IMCE will ever touch; neither is about CELH.
