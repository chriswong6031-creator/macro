# Government Revenue Foresight — session handoff, 2026-08-10 ~12:30Z

Successor to `research/GOVERNMENT_REVENUE_FORESIGHT_HANDOFF_2026-08-09.md` (queue mechanics, §3 rulings, §6 worktree map — all still valid history) and to `research/GOVERNMENT_REVENUE_FORESIGHT_ACCOUNT_HANDOFF.md` (wave specs 10/11/12/13, unchanged). This document records the wave landing, the first-issuance incident, and the corrected first-candidate timeline. **Re-census before acting.**

## §0 Where the program stands

1. **The entire 12-PR wave is MERGED** (2026-08-09 13:20–17:55Z): the reviewed defense19 graph (#5009), the three structural fixes (#5086 enum, #5085 snapshot families, #5090 action-rail identity), grader integrity + GRV_FA1 rail fence (#5038), ledger identity (#5040), 9E/9F (#5021), IDV bridge (#5014), SBIR (#5012), disclosure (#5013), amount guard (#4950). #5034 was closed superseded (main's hermetic construction + "never re-add a live ordering pin" ruling outranks it — see its closing comment). #5131 healed the #4951 schema-requiredness red the same morning.
2. **The lobe HAS issued** — wrongly once, then quarantined. The 2026-08-10 04:15Z cycle (run 31354784751, commit 5fc18d5aac8) published the 8 snapshot-rail HII candidates with `known_at` 2026-08-08T11:58:31 — a BACKDATED first issuance (the §3 anti-backfill violation; the projection state was absent in that run's root, and `prior_state=None` skipped the frozen-clock guard). **#5247 (merged 2026-08-10 12:10Z) is the append-only recovery**: ledger immutable (8 rows preserved, sha `920d840a…`), corrected queue `grcq1-13ec0f36…` active 0 / quarantine 8, corrected detail returns structured 410, bilingual quarantine copy live.
3. **The bypass class is closed** (in #5247): projection state absent + non-empty ledger now hard-raises (`candidate projection has no state receipt`); the same 8 can never re-issue (ledger source-key dedupe); NEW historical candidates require a reviewed **historical-suppression manifest** activated as an exact bijection bound to the exact predecessor generation. That manifest machinery is the reusable instrument every future graph expansion needs (defense20 first).
4. **Workspace truth post-wave**: `coverage.award_events.rejected == 0`, 610 validated / 500 visible (cap). The §1 gap-cycle transient (`rejected: 9`, 13:28Z Aug 9) occurred exactly as predicted and cleared with #5086's merge.

## §1 The corrected first-candidate timeline (dry-run-verified, then incident-verified)

- The 8 snapshot-rail HII candidates (4 `award_obligation_change` + 4 `award_ceiling_change`, basis `source_record_recipient`) were pre-verified by a composed-wave scratch dry-run on 2026-08-09 (492 tests green; observation IDs byte-match the later incident's ledger rows).
- **Legitimate first issuance now requires observations with `known_at` forward of the frozen clock**: i.e. the next nightly collect (~04:00Z) re-observing the HII awards, then one lane cycle. The quarantined 8 stay quarantined; the SAME candidates re-issuing under fresh clocks is correct and expected ("a genuinely new same-candidate observation remains eligible").
- **The ~20 action-rail candidates arrive only after a post-#5090 COLLECT** — award-level identity (`award_recipient_*`, basis `award_level_recipient_at_collection`) is attached at collection time; accrued action rows carry none. Do not read snapshot-only first cycles as a defect.
- ci-pack note: the projection suite (33 tests) runs under `pytest -n 2` (xdist) inside its 15-minute lane; do NOT split it into two jobs — a second job sharing the file pushes the 'tripwires' narrow-diff scope to 145/181, one over `test_ci_pack`'s ≤4/5 skip property (boundary sits at exactly 144/144).

## §2 Rulings in force (unchanged + one addition)

All §3 rulings of the 2026-08-09 handoff stand (integration ruling, named-basis identity, GRV_FA1 rail fence, ledger identity, live-probe philosophy). Addition ratified by #5247's construction: **an erroneous issuance is corrected by append-only quarantine with exact identity/hash binding — never by ledger truncation, never by pretending the issuance did not occur.** The prereg composed to 4.0.0 carrying both the 3.1.0 identity-basis amendment and the 4.0.0 sixteen-findings block.

## §3 Next moves, in order

1. **Verify the first legitimate cycle after tonight's ~04:00Z collect** (§4 checklist of the 2026-08-09 handoff still applies, now with: quarantine 8 preserved, fresh rows appended under forward `known_at`, grader admits action-rail only into GRV_FA1, snapshot rows abstain `family_rail_mismatch`).
2. **Defense20 (BWXT)**: post-#4951 collects now query the alias list; once BWXT recipients appear, run `scripts/propose_government_revenue_recipient_graph.py`, review the worksheet, publish via the curator citing the 2026-08-08 approval precedent (fresh operator ack preferred). Expect BWXT's historical events to need a **historical-suppression manifest** (the #5247 instrument) so the graph expansion cannot re-run the backfill incident. #5040 prerequisite: merged. GE stays `no_exact_match`.
3. **Wave 10 rails 2/4/5**, **Wave 11**, **designer-lane surface pass** (SBIR/IDV/shadow-context labels, `semanticLabel` `delta_*` gaps, fact-grid `slice(0,4)`) — unchanged from the account handoff.
4. Small follow-ups still open: `ceiling_changed` sign-blindness; IDV prime-cut widening decision; the schema-requiredness re-tightening for `recipient_query_terms` (allowed only once the committed manifest carries it — check `freshness.award_events.ingest.coverage_manifest.entities[0]` first).

## §4 Traps this session added to the book

- **Name-based inherited-red exclusion admits new defects inside already-red packs** (#4951's 30 hidden failures; the GR3→GR0 import inversion same day) — diff head vs main failing-test LISTS before trusting any exclusion. Memory: `red-pack-hides-a-new-defect-behind-name-based-exclusion`.
- **A run-level "cancelled" is not a job-level fact** (daily.yml read as dead ×3 while 17/18 jobs succeeded).
- **Main-ref ci.yml/fences dispatches shared one cancel-in-progress group** — five baselines died serially before #5133/#5136/#5140; never dispatch while a proof is in flight.
- **Hosted-runner minutes are a fleet resource**: #5124's all-hosted move exhausted the free tier in hours and froze every ubuntu-latest job start (billing usage API is the diagnostic; the operator's spending limit is the lever).
- **`git checkout --theirs` takes the whole file, not the hunk** — it silently dropped a sibling amendment during a dry-run composition; resolve version-string collisions hunk-by-hunk, keep both amendment bodies.
- **A clean rebase can silently drop a sibling's landed edits** when branch commits rewrite regions the sibling touched — audit `git diff <branch> main -- <files mains siblings touched>` for main-lines absent from the branch, then clear them symbol-by-symbol (line counts over-flag refactors; the 2026-08-09 audit's only true positive out of six suspects was zero after symbol checks).
