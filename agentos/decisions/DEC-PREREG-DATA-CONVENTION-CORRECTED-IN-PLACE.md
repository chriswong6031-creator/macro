---
key: PREREG-DATA-CONVENTION-CORRECTED-IN-PLACE
question: >
  A preregistration's entry rule cited a data-availability convention that was later
  MEASURED WRONG — and the study had already run and published. Does the prereg get
  amended in place, superseded by a new prereg, or re-run with the original results
  relabelled? A prereg is meant to be immutable, so amending one post hoc is a
  governance call, not an editorial one.
answer: >
  Amend IN PLACE, dated, with the retired convention left legible and never rewritten.
  Do not supersede. Do not re-run immediately, but record the re-run obligation as a
  binding citation ban until the underlying artifact is rebuilt. Superseding is
  reserved for changes to the DESIGN — hypotheses, conditioners, horizons, universe,
  controls, statistics, or the promotion bar. Applied to
  research/short_side/SP1_SHORT_PRESSURE_PREREG.md §5B.
rationale: >
  Prereg immutability exists to stop goalposts moving after outcomes are seen. That
  hazard was absent in both directions here, which is what licenses the in-place
  correction. First, the correction makes the test STRICTLY HARDER — the retired FINRA
  lag (settlement + 10 calendar days) landed EARLY, so the corrected 8-session rule
  enters later with less information and removes an advantage; nobody moves a goalpost
  toward themselves. Second, the correction was not authored by the study: PR #5705
  came out of a FINRA-lag audit of two drifting constants and had no contact with SP1's
  outcomes. Third, the change is not a design change at all — §5A's binding clause
  ("first trading day at/after knowable_date, never the settlement date") is untouched
  and its stated purpose is exactly "no look-ahead at the publication boundary"; only
  the parenthetical factual gloss on what knowable_date MEANT was wrong. Correcting a
  wrong factual gloss toward the rule's own stated intent is a correction, not a
  redesign. Immutability is then preserved by NON-DELETION rather than
  non-annotation — silently rewriting the three retired-rule sites would have destroyed
  the very audit trail that lets a reader reconstruct what the study actually ran under.
  The decisive precedent is ORACLE_COMPOUND_GAUNTLET_R1.md, which handled a STRONGER
  case identically: a post-outcome dated blockquote that withdrew a PASS (A9) and
  reversed a verdict (A17), left the original intact, named what still stands, and
  minted no new file.
alternatives:
  - option: Supersede with a new prereg (SP1-B) and freeze the original
    why_not: >
      Misfiles a corrected data convention as a design change. The design is byte-identical —
      no hypothesis, conditioner, horizon, universe, control, statistic, or promotion bar
      moves — and superseding would orphan a null that nothing depends on. Reserve
      supersession for the design surface, where the goalpost hazard is real.
  - option: Re-run SP1-A immediately under the corrected rule and republish
    why_not: >
      Zero governance delta for a real render-budget cost. SP1-A promoted nothing, ranked
      nothing, gated nothing, and filed no DO_NOT_REBUILD row, so no authority state rests
      on the numbers. The panel is gitignored build output; the correct trigger is its next
      rebuild. The obligation is not waived — it is recorded as a citation ban.
  - option: Edit the three retired-rule mentions in place so the doc simply reads correctly
    why_not: >
      The published results were computed under the retired rule. Rewriting it makes those
      numbers unattributable to any stated rule and destroys the audit trail. The retired
      convention must stay legible precisely BECAUSE a run happened under it.
  - option: Leave the prereg alone and note the change only in the code
    why_not: >
      The prereg is the freeze authority and the artifact a successor study reads first. A
      reader would take "settlement + 10d" as the live convention and silently inherit a
      measured look-ahead.
evidence:
  - "PR #5705 — retired FINRA lag measured 3/2/2 days EARLY on settlements 2026-06-30 / 07-15 / 07-31, and before the collector's own capture date on all three"
  - "lib/finra_knowable.py module docstring — the three measurements; KNOWABLE_LAG_SESSIONS = 8"
  - "Measured entry-date blast radius over the 205-settlement schedule: 146 move 1-3 sessions LATER, 0 move earlier (strictly one-directional defect)"
  - "Reconstruction validated on 4 independent anchors vs data/finra/short_interest_panel_coverage.json: 205 settlements, first 2018-01-12, last 2026-07-15, and the 3/2/2 deltas"
  - "scripts/research/sp1_short_pressure_study.py:78 + engine/short_pressure.py read the STORED knowable_date; tests/test_short_pressure.py:113 pins raise-not-degrade"
  - "data/finra/short_interest_panel_coverage.json still records knowable_lag_days: 10 — receipt that the live panel predates the fix"
  - "Precedent: research/ORACLE_COMPOUND_GAUNTLET_R1.md — post-outcome CORRECTION (2026-07-04) + AMENDMENT (2026-07-07) blockquotes, in place, original intact, no new file"
  - "Form precedent: SP1_SHORT_PRESSURE_PREREG.md §5A AMENDMENT 1 (pre-outcome, 2026-08-05)"
affects:
  - "research/short_side/SP1_SHORT_PRESSURE_PREREG.md"
  - "research/*_PREREG.md"
  - "engine/short_pressure.py"
  - "reports/sp1-short-pressure.md"
confidence: high
reversibility: easy
decided_by: session claude/sp1-prereg-knowable-lag-correction
decided_at: 2026-08-14
---

## Effect on the published SP1 result, stated as the ruling requires

The ruling is only meaningful if it answers the blast-radius question explicitly, so
the amendment separates three things that are easy to conflate:

- **Numbers — affected.** `reports/sp1-short-pressure.md`, `data/research/sp1_short_pressure.json`
  and the §7 log were computed under the retired rule. The study reads the panel's stored
  column, so a rebuild changes every number with **no code change to the study**.
- **Verdict — unaffected.** SP1-A is a NULL its own §5A gate already declared
  uninterpretable (H0 did not replicate). §7's two stated reasons — survivorship and
  coverage — are untouched by the lag. The correction changes the numbers, not the reasons
  the verdict was reached.
- **Citability — narrowed.** §5A already forbade quoting SP1-A effect sizes as unbiased on
  survivorship grounds. This adds a second, independent PIT reason, so no number may be
  cited anywhere until a re-run on a rebuilt panel replaces it.

## What is deliberately not claimed

A shifted entry produces genuinely different events, not a monotone transform of the same
ones. No claim is made that a re-run reproduces these numbers or their signs. The honest
statement is directional only: the correction removes an advantage the study already failed
to exploit, so the null is if anything reinforced. If a re-run instead flips H0 to
negative-and-significant, that is a **new finding requiring its own adjudication** — it does
not retroactively validate anything in the original run.

## The standing rule this sets

A prereg whose **data-availability convention** is later measured wrong is corrected in
place, dated, with the retired convention left legible. The correction must say the rule was
**measured wrong and in which direction** — never merely "revised" — and must answer, per
published artifact, whether the numbers, the verdict, or both are affected. Design changes
still supersede.
